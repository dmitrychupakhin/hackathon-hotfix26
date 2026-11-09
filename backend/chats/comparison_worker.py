"""Paired, package-grouped runs; a technical failure never becomes a score."""
import hashlib
import logging
import time

import requests
from django.conf import settings
from django.db import close_old_connections, connections

from .ai_client import ai_request
from .models import ComparisonDocument, ComparisonJob

logger = logging.getLogger(__name__)
FAILED_STATUSES = {'failed', 'cancelled', 'interrupted'}
MODES = ('baseline', 'harness')
WAIT_GRACE_SECONDS = 60


def _advance(job, stage, **updates):
    close_old_connections()
    job.progress.update(updates)
    job.stage = stage
    job.save(update_fields=['progress', 'stage', 'updated_at'])


def _ensure_inputs(job, user_id):
    if job.questions and job.reference_answers and job.progress.get('package_ids'):
        return
    files = dict(job.documents.filter(
        kind__in=[ComparisonDocument.Kind.QUESTIONS, ComparisonDocument.Kind.ANSWERS]
    ).values_list('kind', 'id'))
    parsed = ai_request(
        'POST', '/comparison-inputs/parse', user_id=user_id,
        payload={
            'questions_file_id': str(files[ComparisonDocument.Kind.QUESTIONS]),
            'answers_file_id': str(files[ComparisonDocument.Kind.ANSWERS]),
            'document_file_ids': [str(item) for item in job.documents.filter(
                kind=ComparisonDocument.Kind.DOCUMENT
            ).values_list('id', flat=True)],
            'model': job.model_id,
        },
        timeout=360,
        idempotency_key=f'{job.id}-inputs',
    )
    # These values are parsed by code, never rewritten by a language model.
    job.questions = parsed['questions']
    job.reference_answers = parsed['reference_answers']
    job.progress['package_ids'] = parsed['package_ids']
    job.progress['question_grouping'] = 'per_package'
    job.stage = 'parsed'
    job.save(update_fields=['questions', 'reference_answers', 'progress', 'stage', 'updated_at'])


def _comparison_timeout(job):
    timeout = job.progress.get('run_timeout_seconds')
    if timeout is None:
        # Resuming a legacy run must not rewrite its already submitted budget.
        legacy = any(job.progress.get(f'{mode}_run_id') for mode in MODES)
        timeout = 600 if legacy else max(1, min(3600, settings.AI_COMPARISON_TIMEOUT_SECONDS))
        _advance(job, job.stage, run_timeout_seconds=timeout,
                 wait_timeout_seconds=timeout + WAIT_GRACE_SECONDS)
    return timeout


def _ensure_run(job, user_id, mode):
    key = f'{mode}_run_id'
    run_id = job.progress.get(key)
    if not run_id:
        package_ids = job.progress['package_ids']
        payload = {
            'mode': mode,
            'model': job.model_id,
            'questions': [
                {'id': item['id'], 'package_id': package_ids[item['package_id']], 'text': item['text']}
                for item in job.questions
            ],
            'options': {'question_grouping': 'per_package',
                        'timeout_seconds': _comparison_timeout(job)},
        }
        if mode == 'harness' and job.system_prompt:
            payload['additional_instructions'] = job.system_prompt
        run = ai_request(
            'POST', '/runs', user_id=user_id, payload=payload,
            idempotency_key=f'{job.id}-{mode}',
        )
        run_id = run['id']
        _advance(job, 'running', **{key: run_id})
    return run_id


def _ensure_evaluation(job, user_id, mode):
    key = f'{mode}_evaluation_id'
    evaluation_id = job.progress.get(key)
    if not evaluation_id:
        evaluation = ai_request(
            'POST', f"/runs/{job.progress[f'{mode}_run_id']}/evaluate",
            user_id=user_id,
            payload={'reference_answers': job.reference_answers},
        )
        evaluation_id = evaluation['id']
        _advance(job, 'evaluating', **{key: evaluation_id})
        return evaluation
    return ai_request('GET', f'/evaluations/{evaluation_id}', user_id=user_id)


def _failure(code='run_failed'):
    # Provider exception bodies can contain credentials: expose stable codes only.
    reasons = {
        'provider_unreachable': 'Нет соединения с провайдером модели.',
        'provider_timeout': 'Провайдер не ответил вовремя.',
        'rate_limited': 'Лимит запросов провайдера исчерпан после разрешённых повторов.',
        'context_budget_exceeded': 'Документы не поместились в бюджет контекста этого режима.',
        'context_length_exceeded': 'Провайдер отклонил размер контекста.',
        'output_truncated': 'Ответ модели оборвался по лимиту выходных токенов.',
        'run_timeout': 'Истёк общий лимит времени запуска.',
        'comparison_timeout': 'Истёк срок ожидания сравнения.',
        'baseline_format_invalid': 'Модель не вернула требуемый формат базового ответа.',
    }
    return {'code': code, 'message': reasons.get(code, 'Технический отказ режима.') + ' Оценка не рассчитана.'}


def _run_state(run):
    terminal = run.get('status') == 'completed' or run.get('status') in FAILED_STATUSES
    metrics_final = run.get('_metrics_final', terminal)
    metrics = dict(run.get('metrics') or {})
    started = run.get('_started_model_calls', 0)
    if not metrics_final:
        # Started calls are observable, tokens and costs are not inferred.
        metrics['model_calls'] = max(metrics.get('model_calls') or 0, started)
    return {'status': run.get('status', 'failed'), 'metrics': metrics,
            'metrics_final': metrics_final, 'model_calls_started': started,
            'model_calls_source': 'final_metrics' if metrics_final else 'started_events',
            'step': run.get('_public_step'),
            'error': (run.get('evaluation_error') or
                      (_failure((run.get('error') or {}).get('code', 'run_failed'))
                       if run.get('status') in FAILED_STATUSES else None))}


def _read_progress(job, user_id, mode, run):
    """Replay only public operational steps; never retain prompts/tool payloads."""
    previous = job.progress.get('run_states', {}).get(mode, {})
    run['_public_step'] = previous.get('step')
    run['_started_model_calls'] = previous.get('model_calls_started', 0)
    cursors = job.progress.setdefault('event_cursors', {})
    cursor = cursors.get(mode, 0)
    # Drain terminal tails as well. Bounded pages prevent a corrupt upstream log
    # from indefinitely blocking the comparison worker.
    replay_deadline = time.monotonic() + 3
    for _ in range(100):
        if time.monotonic() >= replay_deadline:
            break
        try:
            page = ai_request('GET', f"/runs/{job.progress[f'{mode}_run_id']}/events?after={cursor}&limit=100",
                              user_id=user_id, timeout=3)
        except (requests.RequestException, RuntimeError, ValueError):
            break
        if not isinstance(page, list) or not page:
            break
        next_cursor = cursor
        for event in page:
            seq = event.get('seq', 0)
            if not isinstance(seq, int) or seq <= cursor:
                continue
            next_cursor = max(next_cursor, seq)
            data = event.get('data') or {}
            if event.get('type') == 'harness.step':
                public = {key: data.get(key) for key in ('title', 'message', 'status', 'kind', 'details')}
                if public['kind'] != 'result' or run['_public_step'] is None:
                    run['_public_step'] = public
            elif event.get('type') == 'llm.started':
                call = data.get('call')
                if isinstance(call, int) and call >= 0:
                    run['_started_model_calls'] = max(run['_started_model_calls'], call)
        if next_cursor == cursor:
            break
        cursor = next_cursor
        cursors[mode] = cursor
        if len(page) < 100:
            break
    return run


def _wait_runs(job, user_id, runs):
    pending = {mode for mode, run in runs.items() if run.get('status') not in FAILED_STATUSES}
    deadline = time.monotonic() + _comparison_timeout(job) + WAIT_GRACE_SECONDS
    while pending and time.monotonic() < deadline:
        for mode in tuple(pending):
            try:
                run = ai_request('GET', f"/runs/{job.progress[f'{mode}_run_id']}", user_id=user_id)
                run['_metrics_final'] = run['status'] == 'completed' or run['status'] in FAILED_STATUSES
                runs[mode] = _read_progress(job, user_id, mode, run)
                if run['status'] == 'completed' or run['status'] in FAILED_STATUSES:
                    pending.remove(mode)
            except (requests.RequestException, RuntimeError, ValueError):
                # A transient polling error is retried within the shared deadline.
                continue
        _advance(job, 'running', run_states={mode: _run_state(run) for mode, run in runs.items()})
        if pending:
            time.sleep(2)
    for mode in pending:
        previous = runs[mode]
        runs[mode] = {**previous, 'status': 'failed', '_metrics_final': False,
                      'error': _failure('comparison_timeout')}
        try:
            ai_request('POST', f"/runs/{job.progress[f'{mode}_run_id']}/cancel", user_id=user_id)
        except (requests.RequestException, RuntimeError, ValueError):
            logger.warning('Could not cancel timed-out comparison mode %s', mode)
    _advance(job, 'evaluating', run_states={mode: _run_state(run) for mode, run in runs.items()})


def _unavailable(job, run):
    return {'available': False, 'status': run.get('status', 'failed'),
            'error': _run_state(run)['error'] or _failure(), 'questions': len(job.questions),
            'n': len(job.questions), 'correct': None, 'errors': None, 'careful': None,
            'trust_index': None, 'by_type': {}, 'rows': [], 'model': job.model_id,
            'run_metrics': run.get('metrics', {}), 'prompt_hashes': run.get('prompt_hashes', {}),
            'grouping': 'per_package'}


def process_comparison(job_id):
    close_old_connections()
    job = None
    try:
        job = ComparisonJob.objects.get(pk=job_id)
        if job.status not in (ComparisonJob.Status.PENDING, ComparisonJob.Status.RUNNING):
            return
        job.status = ComparisonJob.Status.RUNNING
        job.save(update_fields=['status', 'updated_at'])
        user_id = job.owner_id
        _ensure_inputs(job, user_id)
        runs = {}
        for mode in MODES:
            try:
                _ensure_run(job, user_id, mode)
                runs[mode] = {'status': 'queued'}
            except (requests.RequestException, RuntimeError, ValueError):
                logger.exception('Comparison mode %s could not start', mode)
                runs[mode] = {'status': 'failed', 'error': _failure('run_start_failed')}
        _wait_runs(job, user_id, runs)
        evaluations = {}
        for mode in MODES:
            if runs[mode].get('status') != 'completed':
                continue
            try:
                evaluations[mode] = _ensure_evaluation(job, user_id, mode)
            except (requests.RequestException, RuntimeError, ValueError):
                logger.exception('Comparison mode %s evaluation failed', mode)
                runs[mode]['evaluation_error'] = _failure('evaluation_failed')
        result = {'changed_questions': [], 'delta': None,
                  'warning': 'Один или оба режима не завершены: разница не рассчитывается.'}
        if len(evaluations) == 2:
            try:
                result = ai_request(
                    'POST', '/comparisons', user_id=user_id,
                    payload={'before_evaluation_id': evaluations['baseline']['id'],
                             'after_evaluation_id': evaluations['harness']['id']},
                )
            except (requests.RequestException, RuntimeError, ValueError):
                logger.exception('Paired comparison rejected; keeping separate evaluations')
                result['warning'] = 'Парная проверка сопоставимости не пройдена. Оценки отдельных запусков сохранены; разница не рассчитывается.'
        for mode, key in (('baseline', 'before'), ('harness', 'after')):
            evaluation = evaluations.get(mode)
            result[key] = ({**evaluation, 'available': True, 'status': 'completed', 'error': None,
                            'n': evaluation['questions'], 'grouping': 'per_package'}
                           if evaluation else _unavailable(job, runs[mode]))
        result['runs'] = {mode: {'id': job.progress.get(f'{mode}_run_id'),
                                'status': run.get('status'),
                                'answers': run.get('result', {}).get('answers', []),
                                'metrics': run.get('metrics', {}),
                                'prompt_hashes': run.get('prompt_hashes', {})}
                          for mode, run in runs.items()}
        result['protocol'] = {'model': job.model_id, 'question_grouping': 'per_package',
                              'package_ids': job.progress['package_ids'],
                              'questions': len(job.questions),
                              'baseline_checks': False,
                              'profile_instructions': 'harness_additional_only',
                              'profile_instructions_sha256': hashlib.sha256(job.system_prompt.encode()).hexdigest(),
                              'run_timeout_seconds': _comparison_timeout(job),
                              'wait_timeout_seconds': _comparison_timeout(job) + WAIT_GRACE_SECONDS}
        if job.progress.get('recovery_from_job'):
            result['protocol']['recovery_from_job'] = job.progress['recovery_from_job']
            result['protocol']['baseline_reused'] = True
        job.result = result
        close_old_connections()
        job.status = ComparisonJob.Status.COMPLETED
        job.stage = 'completed'
        job.error = ''
        job.progress['run_states'] = {mode: _run_state(run) for mode, run in runs.items()}
        job.save(update_fields=['result', 'status', 'stage', 'progress', 'error', 'updated_at'])
    except Exception:
        logger.exception('AI comparison %s failed', job_id)
        if job is not None:
            close_old_connections()
            job.status = ComparisonJob.Status.FAILED
            job.stage = 'failed'
            job.error = 'Не удалось подготовить сравнение. Требуются исходные questions.csv, answers_public.json и документы с однозначными закупками.'
            job.save(update_fields=['status', 'stage', 'error', 'updated_at'])
    finally:
        connections.close_all()
