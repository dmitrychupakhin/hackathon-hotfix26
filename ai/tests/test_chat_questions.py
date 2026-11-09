import json
from uuid import uuid4

import pytest
from conftest import FakeModel, reply, wait_run
from fastapi.testclient import TestClient
from test_file_preview import source

from app.domain import DomainError
from app.main import create_app
from app.services.chat_questions import ChatPlan, questions_from_plan


def test_model_units_are_lossless_and_server_assigns_ids():
    parts = ["Ответь по документам.\nКакой срок?\nЕсли срок изменён, укажи новый.",
             "Сколько стоит?\nУкажи валюту."]
    text = '\n'.join(parts)
    items = questions_from_plan("message", "package", text, ChatPlan(parts=parts))
    assert [q.id for q in items] == ["message.q01", "message.q02"]
    assert [q.text for q in items] == parts
    assert questions_from_plan("m", "p", text, ChatPlan(parts=[text]))[0].id == "m"


@pytest.mark.parametrize('parts', [
    ['Какой срок?'], ['Какой срок?', 'Сколько стоит?', 'Выдуманный вопрос?'],
    ['Сколько стоит?', 'Какой срок?'], ['Каков срок?', 'Сколько стоит?'],
    ['Какой срок?', 'Какой срок?', 'Сколько стоит?'], [' '],
])
def test_omissions_rewrites_duplicates_and_reordering_are_rejected(parts):
    with pytest.raises(DomainError) as exc:
        questions_from_plan('m', 'p', 'Какой срок? Сколько стоит?', ChatPlan(parts=parts))
    assert exc.value.code == 'invalid_chat_plan'


def test_plan_limit_is_not_silently_truncated():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ChatPlan(parts=['пункт'] * 51)


def test_chat_partial_failure_does_not_discard_accepted_answer(settings, headers):
    def behavior(kwargs, _):
        if kwargs['messages'][0]['content'].startswith('Partition the raw text'):
            return reply({'parts': ['Какой размер обеспечения?', 'Какой срок?']})
        if kwargs["messages"][0]["content"].startswith("Review proposed"):
            body = json.loads(kwargs["messages"][-1]["content"])
            return reply(
                {
                    "reviews": [
                        {"id": a["id"], "verdict": "supported", "reason": "Подтверждено"}
                        for a in body["proposed"]
                    ]
                }
            )
        initial = next(
            json.loads(m["content"])
            for m in kwargs["messages"]
            if m["role"] == "user" and "sources" in json.loads(m["content"])
        )
        latest = json.loads(kwargs["messages"][-1]["content"])
        pending = latest.get("repair_only", [q["id"] for q in initial["questions"]])
        return reply(
            {
                "answers": [
                    dict(
                        id=q["id"],
                        status="ответ",
                        answer="18000 руб.",
                        evidence=[
                            {
                                "span_id": initial["sources"][0]["span_id"]
                                if q == initial["questions"][0]
                                else "invented-span"
                            }
                        ],
                    )
                    for q in initial["questions"]
                    if q["id"] in pending
                ]
            }
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        record, _ = source(client, settings)
        message_id = str(uuid4())
        response = client.post(
            "/api/v1/chat-runs",
            headers=headers,
            json={
                "chat_id": str(uuid4()),
                "message_id": message_id,
                "model": "test-model",
                "file_ids": [record["id"]],
                "question": "Какой размер обеспечения?\nКакой срок?",
            },
        )
        assert response.status_code == 202, response.text
        run = wait_run(client, headers, response.json()["id"])
        first, second = run["result"]["answers"]
        assert first["id"] == f"{message_id}.q01" and first["status"] == "ответ"
        assert first["evidence"][0]["source_file_id"] == record["id"]
        assert second["status"] == "не знаю" and second["origin"] == "fallback"
        assert second["evidence"] == []
        assert any(c["code"] == "unknown_evidence" for c in second["checks"])
        events = client.get(f"/api/v1/runs/{run['id']}/events?limit=500", headers=headers).json()
        completed = [e["data"] for e in events if e["type"] == "answer.completed"]
        assert len(completed) == 2
        assert {e["question_index"] for e in completed} == {0, 1}
        assert all(e["question_count"] == 2 and e["question"]["text"] for e in completed)
        assert run['metrics']['model_calls'] >= 2
        inputs = client.get(f"/api/v1/runs/{run['id']}/inputs", headers=headers).json()
        assert inputs['snapshot']['chat_message']['text'] == 'Какой размер обеспечения?\nКакой срок?'


@pytest.mark.parametrize('text,parts', [
    ('P01-03;P01;Какой размер обеспечения?\nP01-07;P01;Какой срок?',
     ['P01-03;P01;Какой размер обеспечения?', 'P01-07;P01;Какой срок?']),
    ('P01-03\tP01\tКакой размер обеспечения?\nP01-07\tP01\tКакой срок?',
     ['P01-03\tP01\tКакой размер обеспечения?', 'P01-07\tP01\tКакой срок?']),
    ('Укажи обеспечение; затем расскажи про срок исполнения.',
     ['Укажи обеспечение;', 'затем расскажи про срок исполнения.']),
    ('Какой срок? Если продлён, укажи новый. Нужны цитаты из двух документов.',
     ['Какой срок? Если продлён, укажи новый. Нужны цитаты из двух документов.']),
])
def test_chat_uses_model_units_independently_of_text_layout(settings, headers, text, parts):
    model = FakeModel()
    async def behavior(kwargs, _):
        if kwargs['messages'][0]['content'].startswith('Partition the raw text'):
            assert kwargs['messages'][-1]['content'] == text
            return reply({'parts': parts})
        # Every answering and critic call receives the original shared instructions.
        contexts = [json.loads(message['content']) for message in kwargs['messages']
                    if message['role'] == 'user']
        assert any(item.get('content') == text for context in contexts
                   for item in context.get('previous_dialogue_for_reference_only', []))
        return await model.complete(**kwargs)
    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        record, _ = source(client, settings)
        response = client.post('/api/v1/chat-runs', headers=headers, json={
            'chat_id': str(uuid4()), 'message_id': str(uuid4()), 'model': 'test-model',
            'file_ids': [record['id']], 'question': text,
        })
        run = wait_run(client, headers, response.json()['id'])
        assert run['status'] == 'completed', run.get('error')
        assert [q['text'] for q in run['request']['questions']] == parts
        assert len(run['result']['answers']) == len(parts)
        assert all(a['status'] == 'ответ' for a in run['result']['answers'])


def test_invalid_model_plan_retries_then_fails_without_guessing(settings, headers):
    model = FakeModel(lambda kwargs, _: reply({'parts': ['Какой срок?']}))
    with TestClient(create_app(settings, model)) as client:
        record, _ = source(client, settings)
        response = client.post('/api/v1/chat-runs', headers=headers, json={
            'chat_id': str(uuid4()), 'message_id': str(uuid4()), 'model': 'test-model',
            'file_ids': [record['id']], 'question': 'Какой срок? Сколько стоит?',
        })
        run = wait_run(client, headers, response.json()['id'])
        assert run['status'] == 'failed'
        assert run['error']['code'] == 'invalid_chat_plan'
        assert run['metrics']['model_calls'] == 2
        assert all(not call.get('tools') for call in model.calls)


@pytest.mark.parametrize('unsolicited_tool', [False, True])
def test_plan_retry_keeps_only_raw_current_message_not_history_or_bad_plan(settings, headers, unsolicited_tool):
    from app.infrastructure.llm import Reply
    default = FakeModel()
    text = 'P01-03\tP01\tКакое обеспечение?\nP01-04\tP01\tНазови сумму обеспечения.'
    planning = []
    async def behavior(kwargs, _):
        if kwargs['messages'][0]['content'].startswith('Partition the raw text'):
            # JSON wrappers/history and corrective USER messages caused the live
            # failure: the model partitioned those instead of the current message.
            assert [m['content'] for m in kwargs['messages'] if m['role'] == 'user'] == [text]
            assert not any(m['role'] == 'assistant' for m in kwargs['messages'])
            planning.append(True)
            if len(planning) == 1:
                if unsolicited_tool:
                    return Reply({'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': 'unsolicited', 'type': 'function', 'function': {
                            'name': 'calculate', 'arguments': '{}'}}]}, 'tool_calls', 'test-model', {})
                return reply({'parts': ['OLD_HISTORY_NOT_CURRENT_MESSAGE']})
            return reply({'parts': text.splitlines()})
        return await default.complete(**kwargs)
    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        record, _ = source(client, settings)
        response = client.post('/api/v1/chat-runs', headers=headers, json={
            'chat_id': str(uuid4()), 'message_id': str(uuid4()), 'model': 'test-model',
            'file_ids': [record['id']], 'question': text,
            'history': [{'role': 'user', 'content': 'OLD_HISTORY_NOT_CURRENT_MESSAGE'}],
        })
        run = wait_run(client, headers, response.json()['id'])
        assert run['status'] == 'completed', run.get('error')
        assert len(run['result']['answers']) == 2
        assert len(planning) == 2
