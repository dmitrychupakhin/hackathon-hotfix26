"""Render independently checked AI answers as one chat message.

Question text/order come from the submitted run, never from model output.
Only IDs belonging to the current message can be assembled.
"""
from chats.citations import build_citations


CHECK_LABELS = {
    'unknown_evidence': 'ссылка на источник не подтверждена',
    'quote': 'цитата не совпала с документом',
    'numbers': 'числа не подтверждены источниками',
    'calculation': 'расчёт не подтверждён',
    'coverage': 'документы просмотрены не полностью',
    'semantic_review': 'смысловая проверка не пройдена',
    'review_unavailable': 'проверка критиком не завершилась',
    'answer_schema': 'модель вернула неверные идентификаторы или формат ответов',
    'scan_format_invalid': 'модель вернула неверный формат результатов поиска по документам',
    'scan_facts_invalid': 'модель вернула некорректные доказательства из документов',
}

FAILURE_LABELS = {
    'provider_timeout': 'провайдер не ответил вовремя',
    'upstream_timeout': 'провайдер не ответил вовремя',
    'provider_unreachable': 'нет соединения с провайдером',
    'service_unavailable': 'провайдер временно недоступен',
    'rate_limited': 'превышен лимит запросов провайдера',
    'call_budget_exhausted': 'исчерпан бюджет запросов к модели',
    'timeout': 'истекло время выполнения',
    'run_timeout': 'истекло время выполнения запроса',
    'output_truncated': 'ответ модели оборвался из-за ограничения длины',
    'context_budget_exceeded': 'превышен доступный размер контекста',
    'scan_format_invalid': CHECK_LABELS['scan_format_invalid'],
    'scan_facts_invalid': CHECK_LABELS['scan_facts_invalid'],
}


def failure_label(code):
    if isinstance(code, str):
        prefix = code.partition(':')[0]
        if prefix in {'scan_format_invalid', 'scan_facts_invalid'}:
            code = prefix
    return FAILURE_LABELS.get(code)


def check_label(check):
    label = CHECK_LABELS.get(check.get('code'))
    if check.get('code') == 'review_unavailable':
        cause = failure_label(check.get('message'))
        if cause:
            return f'{label}: {cause}'
    return label


def display_answer(answer):
    if answer.get('status') == 'не знаю':
        if answer.get('clarification_question'):
            return answer['clarification_question']
        if answer.get('origin') == 'fallback':
            if answer.get('reason') == 'invalid_chat_plan':
                return 'Не удалось подготовить отдельные ответы без потери части сообщения. Ответы не проверены.'
            reasons = list(dict.fromkeys(
                label for check in answer.get('checks', [])
                if check.get('passed') is False and (label := check_label(check))
            ))
            suffix = '; '.join(reasons) or failure_label(answer.get('reason')) or 'проверка не завершилась'
            return f'Не удалось подтвердить ответ: {suffix}.'
        return 'Не знаю: недостаточно подтверждённых данных.'
    return answer.get('answer') or answer.get('status') or ''


def compose_chat_answer(result, message_id, chat):
    answers = result.get('result', {}).get('answers') or []
    single = next((a for a in answers if a.get('id') == message_id), None)
    questions = result.get('request', {}).get('questions') or []
    if len(questions) < 2:
        if single is None:
            return None
        return display_answer(single), single, build_citations(single, chat)
    # AI may not attach unrelated answers to a user's message.
    expected_ids = [f'{message_id}.q{index:02d}' for index in range(1, len(questions) + 1)]
    if [q.get('id') for q in questions] != expected_ids or len(questions) > 50:
        return None
    by_id = {answer.get('id'): answer for answer in answers}
    parts, citations, evidence = [], {}, []
    for question in questions:
        answer = by_id.get(question['id']) or {
            'id': question['id'], 'status': 'не знаю', 'origin': 'fallback',
            'reason': 'missing_answer', 'checks': [], 'evidence': [],
        }
        sources = build_citations(answer, chat)
        citations.update((citation['id'], citation) for citation in sources)
        evidence.extend(answer.get('evidence') or [])
        parts.append({
            **answer, 'question': question['text'],
            'display_answer': display_answer(answer),
            'citation_ids': [citation['id'] for citation in sources],
        })
    content = '\n\n'.join(
        f"{index}. {part['question']}\n{part['display_answer']}"
        for index, part in enumerate(parts, 1)
    )
    known = [part for part in parts if part.get('status') in ('ответ', 'расхождение', 'нет в документах')]
    payload = {
        'id': message_id, 'answer': content,
        'status': 'ответ' if known else 'не знаю',
        'partial': len(known) != len(parts) or any(
            part.get('reason') == 'independent_review_incomplete' for part in parts
        ), 'parts': parts, 'evidence': evidence,
    }
    return content, payload, list(citations.values())
