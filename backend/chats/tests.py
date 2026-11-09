import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chats.citations import build_citations
from chats.answers import compose_chat_answer, display_answer
from chats.management.commands.run_chat_worker import _submit_pending, sync_run
from chats.models import Chat, ChatFile, ChatMessage, ChatRun
from users.models import User


class DocumentPreviewTests(TestCase):
    def test_review_failure_displays_safe_underlying_cause(self):
        text = display_answer({'status': 'не знаю', 'origin': 'fallback', 'checks': [
            {'code': 'review_unavailable', 'passed': False, 'message': 'scan_format_invalid'}]})
        self.assertIn('неверный формат результатов поиска', text)
        self.assertNotIn('лимитов', text)
        text = display_answer({'status': 'не знаю', 'origin': 'fallback', 'checks': [
            {'code': 'review_unavailable', 'passed': False,
             'message': 'scan_format_invalid:foreign_span_ids:PRIVATE'}]})
        self.assertIn('неверный формат результатов поиска', text)
        self.assertNotIn('PRIVATE', text)
        self.assertNotIn('foreign_span_ids', text)
        text = display_answer({'status': 'не знаю', 'origin': 'fallback', 'checks': [
            {'code': 'review_unavailable', 'passed': False, 'message': 'provider_timeout'}]})
        self.assertIn('провайдер не ответил вовремя', text)
        text = display_answer({'status': 'не знаю', 'origin': 'fallback', 'checks': [
            {'code': 'review_unavailable', 'passed': False, 'message': 'PRIVATE provider response'}]})
        self.assertNotIn('PRIVATE', text)
        self.assertIn('проверка критиком не завершилась', text)

    def test_format_failure_is_not_reported_as_limit_exhaustion(self):
        text = display_answer({'status': 'не знаю', 'origin': 'fallback',
                               'reason': 'scan_format_invalid', 'checks': []})
        self.assertIn('неверный формат', text)
        self.assertNotIn('лимитов', text)
        for code, expected in [('scan_facts_invalid', 'некорректные доказательства'),
                               ('output_truncated', 'ограничения длины'),
                               ('run_timeout', 'истекло время')]:
            with self.subTest(code=code):
                text = display_answer({'status': 'не знаю', 'origin': 'fallback',
                                       'reason': code, 'checks': []})
                self.assertIn(expected, text)

    def test_batch_answer_with_incomplete_review_remains_partial_without_warning(self):
        message_id = str(uuid4())
        questions = [
            {'id': f'{message_id}.q01', 'text': 'Какой размер?'},
            {'id': f'{message_id}.q02', 'text': 'Какой срок?'},
        ]
        answers = [
            {'id': questions[0]['id'], 'status': 'ответ', 'answer': '18000 рублей',
             'reason': 'independent_review_incomplete', 'checks': [
                 {'code': 'review_unavailable', 'passed': False, 'message': 'provider_timeout'},
             ]},
            {'id': questions[1]['id'], 'status': 'ответ', 'answer': '30 дней'},
        ]
        content, payload, citations = compose_chat_answer(
            {'request': {'questions': questions}, 'result': {'answers': answers}},
            message_id, self.chat,
        )
        self.assertEqual(content, '1. Какой размер?\n18000 рублей\n\n2. Какой срок?\n30 дней')
        self.assertTrue(payload['partial'])
        self.assertEqual(payload['status'], 'ответ')
        self.assertEqual(payload['parts'][0]['checks'], answers[0]['checks'])
        self.assertEqual(citations, [])

    def test_invalid_chat_plan_is_not_presented_as_missing_facts(self):
        text = display_answer({'status': 'не знаю', 'origin': 'fallback',
                               'reason': 'invalid_chat_plan', 'checks': []})
        self.assertIn('без потери части сообщения', text)
        text = display_answer({'status': 'не знаю', 'origin': 'fallback', 'checks': [
            {'code': 'answer_schema', 'passed': False}]})
        self.assertIn('идентификаторы', text)

    @patch('chats.management.commands.run_chat_worker.ai_request')
    def test_failed_planning_keeps_original_message_and_reports_clear_error(self, ai_request):
        message = ChatMessage.objects.create(chat=self.chat, role='user', content='CSV вопрос')
        run = ChatRun.objects.create(chat=self.chat, user_message=message, status='running', ai_run_id='bad-plan')
        ai_request.return_value = {'status': 'failed', 'error': {'code': 'invalid_chat_plan', 'message': 'Invalid partition'}}
        sync_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertIn('без потери части сообщения', run.error)
        self.assertIsNone(run.assistant_message_id)
        self.assertEqual(run.user_message.content, 'CSV вопрос')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        setting = override_settings(MEDIA_ROOT=self.directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.user = User.objects.create_user('owner@example.test')
        self.other = User.objects.create_user('other@example.test')
        self.chat = Chat.objects.create(owner=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.attachment = self.make_file('notice.pdf', b'%PDF-local')

    def make_file(self, name, content):
        return ChatFile.objects.create(
            chat=self.chat, file=SimpleUploadedFile(name, content), original_name=name,
            size=len(content), sha256=hashlib.sha256(content).hexdigest(),
        )

    def url(self, suffix='preview', file=None):
        return f'/api/chats/{self.chat.pk}/files/{(file or self.attachment).pk}/{suffix}'

    def preview(self, **kwargs):
        return dict(file_id=str(self.attachment.pk), name='notice.pdf', format='pdf',
                    text='🙂 Обеспечение 18000 рублей.', text_sha256='a' * 64,
                    original_sha256=self.attachment.sha256, version=self.attachment.sha256,
                    locations=[{'page': 1, 'start': 0, 'end': 28}], partial=False,
                    warnings=[], offset_unit='unicode_code_points', **kwargs)

    @patch('chats.views.ai_request')
    def test_preview_owner_isolation_and_expected_revision(self, ai_request):
        ai_request.return_value = self.preview()
        response = self.client.get(self.url(), {'text_sha256': 'a' * 64, 'version': self.attachment.sha256})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'notice.pdf')
        self.assertEqual(response.data['content_url'], self.url('content'))
        self.assertIn('text_sha256=', ai_request.call_args.args[1])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.client.get(self.url('content')).status_code, 404)
        self.assertEqual(ai_request.call_count, 1)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    @patch('chats.views.ai_request')
    def test_stale_preview_is_never_navigated(self, ai_request):
        ai_request.return_value = {**self.preview(), 'version': 'old'}
        self.assertEqual(self.client.get(self.url()).status_code, 409)
        error = requests.HTTPError(response=requests.Response())
        error.response.status_code = 409
        ai_request.side_effect = error
        self.assertEqual(self.client.get(self.url()).status_code, 409)
        self.assertEqual(self.client.get(self.url('content'), {'text_sha256': 'a' * 64}).status_code, 409)
        self.assertEqual(self.client.get(self.url(), {'text_sha256': 'not-a-hash'}).status_code, 400)

    def test_pdf_and_docx_remain_original_inline_and_detect_changed_original(self):
        for name, body, mime in [('notice.pdf', b'%PDF-test', 'application/pdf'),
                                 ('notice.docx', b'PK-local-docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')]:
            attachment = self.make_file(name, body)
            response = self.client.get(self.url('content', attachment))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), body)
            self.assertEqual(response['Content-Type'], mime)
            self.assertIn('inline', response['Content-Disposition'])
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            Path(attachment.file.path).write_bytes(b'changed')
            self.assertEqual(self.client.get(self.url('content', attachment)).status_code, 409)

    @patch('chats.views.ai_request')
    def test_other_formats_serve_canonical_text_not_original_markup(self, ai_request):
        attachment = self.make_file('notice.html', b'<b>text</b>')
        ai_request.return_value = {**self.preview(), 'file_id': str(attachment.pk),
                                  'original_sha256': attachment.sha256, 'version': attachment.sha256,
                                  'text': 'text', 'format': 'txt'}
        response = self.client.get(self.url('content', attachment))
        self.assertEqual(b''.join(response.streaming_content), b'text')
        self.assertTrue(response['Content-Type'].startswith('text/plain'))

    @patch('chats.management.commands.run_chat_worker.ai_request')
    def test_full_answer_and_citations_survive_history_reload(self, ai_request):
        question = ChatMessage.objects.create(chat=self.chat, role='user', content='Сколько?')
        run = ChatRun.objects.create(chat=self.chat, user_message=question, status='running', ai_run_id='run-1')
        quote = '18000 рублей'
        span = dict(id='span-1', document_id=str(self.attachment.pk), file='ignored.pdf',
                    source_file_id=str(self.attachment.pk), source_hash='a' * 64,
                    source_version=self.attachment.sha256, original_sha256=self.attachment.sha256,
                    start=15, end=15 + len(quote), text=quote,
                    locations=[{'page': 2, 'start': 0, 'end': 100}])
        answer = dict(id=str(question.id), answer='18000 рублей', status='ответ',
                      evidence=[span, span], checks=[{'code': 'quote', 'passed': True}])
        ai_request.return_value = {'status': 'completed', 'result': {'answers': [answer]}, 'model': 'test-model'}
        sync_run(run)
        response = self.client.get(f'/api/chats/{self.chat.pk}/messages')
        assistant = next(item for item in response.data['results'] if item['role'] == 'assistant')
        self.assertEqual(assistant['answer_payload'], answer)
        self.assertEqual(len(assistant['citations']), 1)
        citation = assistant['citations'][0]
        self.assertEqual(citation['file_name'], 'notice.pdf')
        self.assertEqual(citation['quote'], quote)
        self.assertEqual(citation['offset_unit'], 'unicode_code_points')
        self.assertTrue(citation['preview_url'].startswith(self.url() + '?'))
        self.assertEqual(build_citations({'evidence': [{**span, 'source_file_id': str(uuid4())}]}, self.chat), [])
        self.assertEqual(build_citations({'evidence': [{**span, 'source_version': 'old'}]}, self.chat), [])
        self.assertEqual(build_citations({'evidence': [{**span, 'end': 999}]}, self.chat), [])
        # Retried polling never creates duplicate assistant answers.
        sync_run(run)
        self.assertEqual(self.chat.messages.filter(role='assistant').count(), 1)
        self.assertEqual(self.client.get(f'/api/chats/{self.chat.pk}').data['latest_run']['id'], str(run.id))

    @patch('chats.views.ai_request')
    def test_run_event_replay_is_owner_scoped(self, ai_request):
        message = ChatMessage.objects.create(chat=self.chat, role='user', content='Вопрос')
        run = ChatRun.objects.create(chat=self.chat, user_message=message)
        url = f'/api/chats/{self.chat.pk}/runs/{run.id}/events'
        self.assertEqual(self.client.get(url).data, [])
        run.ai_run_id = 'trusted-ai-run'
        run.save()
        ai_request.return_value = [{'seq': 5, 'type': 'harness.step', 'data': {'title': 'Проверка'}}]
        self.assertEqual(self.client.get(url, {'after': 4, 'limit': 10}).status_code, 200)
        self.assertEqual(ai_request.call_args.args[1], '/runs/trusted-ai-run/events?after=4&limit=10')
        self.assertEqual(self.client.get(url, {'after': -1}).status_code, 400)
        self.assertEqual(self.client.get(url, {'limit': 500}).status_code, 200)
        self.assertEqual(self.client.get(url, {'limit': 501}).status_code, 400)
        self.assertEqual(self.client.get(url, {'limit': 1000}).status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    @patch('chats.management.commands.run_chat_worker.ai_request')
    def test_code_checked_answer_keeps_citations_when_independent_review_unavailable(self, ai_request):
        message = ChatMessage.objects.create(chat=self.chat, role='user', content='Сколько?')
        run = ChatRun.objects.create(chat=self.chat, user_message=message, status='running', ai_run_id='review-timeout')
        quote = '18000 рублей'
        span = dict(source_file_id=str(self.attachment.id), original_sha256=self.attachment.sha256,
                    source_version=self.attachment.sha256, source_hash='a' * 64,
                    start=10, end=10 + len(quote), text=quote)
        answer = dict(id=str(message.id), status='ответ', answer=quote, evidence=[span],
                      reason='independent_review_incomplete', origin='model', checks=[
                          {'code': 'quote', 'passed': True},
                          {'code': 'review_unavailable', 'passed': False, 'message': 'provider_timeout'},
                      ])
        ai_request.return_value = {'status': 'completed', 'result': {'answers': [answer]}}
        sync_run(run)
        response = self.client.get(f'/api/chats/{self.chat.pk}/messages')
        assistant = next(item for item in response.data['results'] if item['role'] == 'assistant')
        self.assertEqual(assistant['content'], quote)
        self.assertEqual(assistant['answer_payload'], answer)
        self.assertEqual(len(assistant['citations']), 1)
        self.assertEqual(assistant['citations'][0]['quote'], quote)
        self.assertTrue(assistant['citations'][0]['preview_url'].startswith(self.url() + '?'))

    @patch('chats.management.commands.run_chat_worker.ai_request')
    def test_batch_answers_preserve_partial_results_and_citation_associations(self, ai_request):
        message = ChatMessage.objects.create(chat=self.chat, role='user', content='Какой размер?\nКакой срок?')
        run = ChatRun.objects.create(chat=self.chat, user_message=message, status='running', ai_run_id='batch')
        first, second = f'{message.id}.q01', f'{message.id}.q02'
        quote = '18000 рублей'
        span = dict(source_file_id=str(self.attachment.id), original_sha256=self.attachment.sha256,
                    source_version=self.attachment.sha256, source_hash='a' * 64,
                    start=10, end=10 + len(quote), text=quote)
        ai_request.return_value = {'status': 'completed', 'request': {'questions': [
            {'id': first, 'text': 'Какой размер?'}, {'id': second, 'text': 'Какой срок?'},
        ]}, 'result': {'answers': [
            {'id': second, 'status': 'не знаю', 'origin': 'fallback', 'checks': [{'code': 'quote', 'passed': False}]},
            {'id': first, 'status': 'ответ', 'answer': '18000 рублей', 'evidence': [span]},
        ]}}
        sync_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, 'completed')
        assistant = run.assistant_message
        self.assertIn('18000 рублей', assistant.content)
        self.assertIn('цитата не совпала', assistant.content)
        self.assertTrue(assistant.answer_payload['partial'])
        parts = assistant.answer_payload['parts']
        self.assertEqual([p['id'] for p in parts], [first, second])
        self.assertEqual(parts[0]['citation_ids'], [assistant.citations[0]['id']])
        self.assertEqual(parts[1]['citation_ids'], [])
        sync_run(run)
        self.assertEqual(self.chat.messages.filter(role='assistant').count(), 1)

    @patch('chats.management.commands.run_chat_worker.ai_request')
    @patch('chats.management.commands.run_chat_worker.close_old_connections')
    def test_long_batch_reply_does_not_break_next_submission_or_truncate_database_history(self, close_connections, ai_request):
        previous = ChatMessage.objects.create(chat=self.chat, role='assistant', content='А' * 20000)
        current = ChatMessage.objects.create(chat=self.chat, role='user', content='А какой срок?')
        run = ChatRun.objects.create(chat=self.chat, user_message=current,
                                    input_snapshot={'history_ids': [str(previous.id)], 'file_ids': []})
        ai_request.return_value = {'id': 'next-run', 'status': 'queued'}
        _submit_pending(run)
        self.assertEqual(len(ai_request.call_args.kwargs['payload']['history'][0]['content']), 12000)
        previous.refresh_from_db()
        self.assertEqual(len(previous.content), 20000)
