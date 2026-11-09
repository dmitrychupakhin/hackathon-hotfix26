import logging
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections, transaction

from chats.ai_client import ai_request
from chats.comparison_worker import process_comparison
from chats.answers import compose_chat_answer
from chats.models import ChatMessage, ChatRun, ComparisonJob

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = ('completed', 'failed', 'cancelled', 'interrupted')


def submit_pending(run_id):
    close_old_connections()
    try:
        run = ChatRun.objects.select_related('chat', 'user_message').get(pk=run_id)
        if run.status == ChatRun.Status.PENDING:
            _submit_pending(run)
    finally:
        connections.close_all()


def _submit_pending(run):
    message = run.user_message
    chat = run.chat
    history_by_id = {
        str(item.id): item for item in ChatMessage.objects.filter(
            pk__in=run.input_snapshot['history_ids'], chat=chat,
        )
    }
    history = [history_by_id[item_id] for item_id in run.input_snapshot['history_ids']]
    payload = {
        'chat_id': str(chat.id),
        'message_id': str(message.id),
        'question': message.content,
        'model': message.model_id,
        'file_ids': run.input_snapshot['file_ids'],
        # A multi-question assistant reply can exceed the per-message wire limit.
        # Keep the full history in PostgreSQL; old generated text is context only.
        'history': [{'role': item.role, 'content': item.content[:12000]} for item in history],
        'system_prompt': run.input_snapshot.get('system_prompt', ''),
    }
    try:
        result = ai_request(
            'POST', '/chat-runs', user_id=chat.owner_id, payload=payload,
            timeout=320, idempotency_key=message.id,
        )
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if 400 <= code < 500 and code != 429:
            ChatRun.objects.filter(pk=run.pk, status=ChatRun.Status.PENDING).update(
                status=ChatRun.Status.FAILED,
                error='AI отклонил запрос или не смог обработать файлы.',
            )
        else:
            logger.warning('AI submission failed for %s: HTTP %s', run.pk, code)
        return
    except (requests.RequestException, RuntimeError, ValueError):
        logger.exception('AI submission failed for %s', run.pk)
        return
    close_old_connections()
    with transaction.atomic():
        current = ChatRun.objects.select_for_update().filter(pk=run.pk).first()
        cancelled = current is None or current.status == ChatRun.Status.CANCELLED
        if current is not None:
            current.ai_run_id = result['id']
            if current.status == ChatRun.Status.PENDING:
                current.status = result['status']
            current.save(update_fields=['ai_run_id', 'status', 'updated_at'])
    if cancelled:
        try:
            ai_request('POST', f"/runs/{result['id']}/cancel", user_id=chat.owner_id)
        except requests.RequestException:
            logger.exception('Could not cancel AI run %s', result['id'])


def sync_run(run):
    try:
        result = ai_request('GET', f'/runs/{run.ai_run_id}', user_id=run.chat.owner_id)
    except (requests.RequestException, RuntimeError, ValueError):
        logger.exception('Could not read AI run %s', run.ai_run_id)
        return
    status = result['status']
    with transaction.atomic():
        current = ChatRun.objects.select_for_update().filter(pk=run.pk).first()
        if current is None or current.status in TERMINAL_STATUSES:
            return
        current.status = status
        if status == ChatRun.Status.COMPLETED:
            composed = compose_chat_answer(result, str(current.user_message_id), current.chat)
            if composed is None:
                current.status = ChatRun.Status.FAILED
                current.error = 'AI не вернул ответ на сообщение.'
            else:
                content, answer, citations = composed
                assistant = ChatMessage.objects.create(
                    chat=current.chat,
                    role=ChatMessage.Role.ASSISTANT,
                    content=content,
                    answer_payload=answer,
                    citations=citations,
                    model_id=result.get('model') or current.user_message.model_id,
                )
                current.assistant_message = assistant
                current.chat.save(update_fields=['updated_at'])
        elif status in TERMINAL_STATUSES:
            ai_error = result.get('error') or {}
            current.error = (
                'Не удалось подготовить отдельные ответы без потери части сообщения. Попробуйте отправить сообщение повторно.'
                if ai_error.get('code') == 'invalid_chat_plan'
                else ai_error.get('message') or 'AI не смог завершить ответ.'
            )
        current.save(update_fields=['status', 'error', 'assistant_message', 'updated_at'])


class Command(BaseCommand):
    help = 'Отправляет сообщения в AI и сохраняет завершённые ответы в Django.'

    def handle(self, *args, **options):
        with ThreadPoolExecutor(max_workers=2) as submissions, ThreadPoolExecutor(max_workers=1) as comparisons:
            inflight = {}
            comparison_future = None
            while True:
                close_old_connections()
                if comparison_future is not None and comparison_future.done():
                    try:
                        comparison_future.result()
                    except Exception:
                        logger.exception('Comparison worker failed unexpectedly')
                    comparison_future = None
                if comparison_future is None:
                    comparison_id = ComparisonJob.objects.filter(
                        status__in=(ComparisonJob.Status.PENDING, ComparisonJob.Status.RUNNING),
                    ).order_by('created_at').values_list('id', flat=True).first()
                    if comparison_id is not None:
                        comparison_future = comparisons.submit(process_comparison, comparison_id)
                for run_id, future in list(inflight.items()):
                    if future.done():
                        try:
                            future.result()
                        except Exception:
                            logger.exception('Could not submit chat run %s', run_id)
                        del inflight[run_id]
                available = 2 - len(inflight)
                if available:
                    pending = ChatRun.objects.filter(status=ChatRun.Status.PENDING).order_by('created_at')[:10]
                    for run_id in pending.values_list('id', flat=True):
                        if run_id not in inflight:
                            inflight[run_id] = submissions.submit(submit_pending, run_id)
                            available -= 1
                            if not available:
                                break
                active = ChatRun.objects.filter(
                    status__in=(ChatRun.Status.QUEUED, ChatRun.Status.RUNNING),
                    ai_run_id__isnull=False,
                ).select_related('chat').order_by('created_at')[:50]
                for run in active:
                    sync_run(run)
                time.sleep(2)
