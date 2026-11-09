import csv
import io
import json
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chats.comparison_worker import _ensure_inputs, _ensure_run, _read_progress, _run_state, process_comparison
from chats.models import AIModel, ComparisonDocument, ComparisonJob
from chats.serializers import ComparisonCreateSerializer
from users.models import User


class ComparisonTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('comparison-owner@example.test')
        self.other = User.objects.create_user('comparison-other@example.test')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        AIModel.objects.get_or_create(id='local-test-model', defaults={'name': 'Local test'})
        self.job = ComparisonJob.objects.create(
            owner=self.user, model_id='local-test-model', system_prompt='User preferences',
            questions=[{'id': 'P01-01', 'package_id': 'P01', 'text': 'Размер?'}],
            reference_answers=[{'id': 'P01-01', 'package': 'P01', 'expected': [18000]}],
            progress={'package_ids': {'P01': str(uuid4())}},
        )

    def test_upload_requires_original_csv_json_and_allows_zip(self):
        def inputs(questions='questions.csv', answers='answers_public.json'):
            return {'questions': SimpleUploadedFile(questions, b'id;package;question\nP01-01;P01;?'),
                    'answers': SimpleUploadedFile(answers, b'[]'),
                    'documents': [SimpleUploadedFile('documents.zip', b'PK-local')],
                    'model_id': 'local-test-model'}
        self.assertTrue(ComparisonCreateSerializer(data=inputs()).is_valid())
        for q, a, field in [('questions.pdf', 'answers_public.json', 'questions'),
                             ('questions.csv', 'answers.txt', 'answers')]:
            serializer = ComparisonCreateSerializer(data=inputs(q, a))
            self.assertFalse(serializer.is_valid())
            self.assertIn(field, serializer.errors)

    @patch('chats.comparison_worker.close_old_connections')
    @patch('chats.comparison_worker.ai_request')
    def test_run_preserves_ids_grouping_and_adds_profile_only_to_harness(self, ai_request, close_connections):
        ai_request.side_effect = [{'id': 'base'}, {'id': 'harness'}]
        for mode in ('baseline', 'harness'):
            _ensure_run(self.job, self.user.id, mode)
        before, after = [c.kwargs['payload'] for c in ai_request.call_args_list]
        self.assertEqual(before['questions'], after['questions'])
        self.assertEqual(before['questions'][0]['id'], 'P01-01')
        self.assertEqual(before['questions'][0]['package_id'], self.job.progress['package_ids']['P01'])
        self.assertEqual(before['options'], {'question_grouping': 'per_package', 'timeout_seconds': 1200})
        self.assertNotIn('additional_instructions', before)
        self.assertNotIn('system_prompt', after)
        self.assertEqual(after['additional_instructions'], 'User preferences')
        self.assertEqual(before['model'], after['model'])

    @patch('chats.comparison_worker.ai_request')
    def test_input_parser_receives_documents_and_stores_original_mapping(self, ai_request):
        self.job.questions = []
        self.job.reference_answers = []
        for kind in ComparisonDocument.Kind.values:
            ComparisonDocument.objects.create(comparison=self.job, kind=kind, file='unused',
                                              original_name=kind, size=1, sha256='a' * 64)
        expected = {'questions': [{'id': 'P02-09', 'package_id': 'P02', 'text': 'Оригинал?'}],
                    'reference_answers': [{'id': 'P02-09', 'package': 'P02', 'expected': [5]}],
                    'package_ids': {'P02': str(uuid4())}}
        ai_request.return_value = expected
        _ensure_inputs(self.job, self.user.id)
        self.assertEqual(len(ai_request.call_args.kwargs['payload']['document_file_ids']), 1)
        self.job.refresh_from_db()
        self.assertEqual(self.job.questions, expected['questions'])
        self.assertEqual(self.job.reference_answers, expected['reference_answers'])
        self.assertEqual(self.job.progress['package_ids'], expected['package_ids'])

    @patch('chats.comparison_worker.connections.close_all')
    @patch('chats.comparison_worker.close_old_connections')
    @patch('chats.comparison_worker.ai_request')
    def test_failed_baseline_keeps_completed_harness_without_fake_delta(self, ai_request, close_connections, close_all):
        evaluation = {'id': 'eval-h', 'questions': 1, 'correct': 1, 'errors': 0, 'careful': 0,
                      'trust_index': 100, 'rows': [{'id': 'P01-01', 'verdict': 'верно'}]}
        answers = [{'id': 'P01-01', 'status': 'ответ', 'answer': '18000 руб.',
                    'quote': '18 000,00', 'file': '01_notice.txt', 'checks': []}]
        def respond(method, path, **kwargs):
            if '/events?' in path:
                return []
            if method == 'POST' and path == '/runs':
                return {'id': kwargs['payload']['mode']}
            if path == '/runs/baseline':
                return {'status': 'failed', 'error': {'code': 'context_budget_exceeded', 'message': 'private-provider-body'},
                        'metrics': {'model_calls': 0}, 'result': {'answers': []}}
            if path == '/runs/harness':
                return {'status': 'completed', 'metrics': {'model_calls': 2}, 'result': {'answers': answers}}
            if path == '/runs/harness/evaluate':
                return evaluation
            self.fail(f'Unexpected request: {method} {path}')
        ai_request.side_effect = respond
        process_comparison(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'completed')
        before, after = self.job.result['before'], self.job.result['after']
        self.assertFalse(before['available'])
        self.assertIsNone(before['trust_index'])
        self.assertIsNone(before['correct'])
        self.assertTrue(after['available'])
        self.assertEqual(after['trust_index'], 100)
        self.assertIsNone(self.job.result['delta'])
        self.assertEqual(self.job.result['runs']['harness']['answers'], answers)
        self.assertNotIn('private-provider-body', json.dumps(self.job.result))
        serialized = self.client.get(f'/api/comparisons/{self.job.id}').data
        self.assertIsNone(serialized['result']['before']['errors'])
        self.assertEqual(serialized['progress']['question_grouping'] if 'question_grouping' in serialized['progress'] else 'per_package', 'per_package')
        self.assertEqual(serialized['progress']['run_states']['harness']['status'], 'completed')

    def test_exports_preserve_csv_contract_are_owner_scoped_and_block_failed_mode(self):
        answer = {'id': 'P01-01', 'status': 'ответ', 'answer': '18;000 руб.',
                  'quote': 'Первая\nвторая', 'file': 'notice.txt', 'evidence': [{'text': 'Первая\nвторая'}]}
        self.job.result = {'runs': {'baseline': {'status': 'failed', 'answers': []},
                                   'harness': {'status': 'completed', 'answers': [answer]}}}
        self.job.save()
        base = f'/api/comparisons/{self.job.id}'
        self.assertEqual(self.client.get(base + '/answers.csv', {'mode': 'baseline'}).status_code, 409)
        self.assertEqual(self.client.get(base + '/answers.csv', {'mode': 'invalid'}).status_code, 400)
        response = self.client.get(base + '/answers.csv', {'mode': 'harness'})
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.content.decode()), delimiter=';'))
        self.assertEqual(list(rows[0]), ['id', 'status', 'answer', 'quote', 'file'])
        self.assertEqual(rows[0]['answer'], '18;000 руб.')
        self.assertEqual(rows[0]['quote'], 'Первая вторая')
        report = self.client.get(base + '/report.json')
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()['result']['runs']['harness']['answers'][0]['quote'], answer['quote'])
        self.assertNotIn('system_prompt', report.json())
        for suffix in ('/answers.csv?mode=harness', '/report.json'):
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.get(base + suffix).status_code, 404)
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(base + suffix).status_code, 401)


    @patch('chats.comparison_worker.connections.close_all')
    @patch('chats.comparison_worker.close_old_connections')
    @patch('chats.comparison_worker.ai_request')
    def test_pair_mismatch_retains_both_scores_and_completed_answers(self, ai_request, close_connections, close_all):
        def respond(method, path, **kwargs):
            if '/events?' in path:
                return []
            if path == '/runs' and method == 'POST':
                return {'id': kwargs['payload']['mode']}
            if path.endswith('/evaluate'):
                return {'id': path.split('/')[2] + '-eval', 'questions': 1, 'correct': 1,
                        'errors': 0, 'careful': 0, 'trust_index': 100, 'rows': []}
            if path == '/comparisons':
                raise ValueError('different_inputs')
            return {'status': 'completed', 'result': {'answers': [{'id': 'P01-01', 'status': 'ответ'}]}}
        ai_request.side_effect = respond
        with self.assertLogs('chats.comparison_worker', level='ERROR'):
            process_comparison(self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'completed')
        self.assertIsNone(self.job.result['delta'])
        self.assertTrue(self.job.result['before']['available'])
        self.assertTrue(self.job.result['after']['available'])
        self.assertIn('сопоставимости', self.job.result['warning'])

    @patch('chats.comparison_worker.connections.close_all')
    @patch('chats.comparison_worker.close_old_connections')
    @patch('chats.comparison_worker.ai_request')
    def test_evaluation_failure_does_not_discard_generated_csv(self, ai_request, close_connections, close_all):
        def respond(method, path, **kwargs):
            if '/events?' in path:
                return []
            if path == '/runs' and method == 'POST':
                return {'id': kwargs['payload']['mode']}
            if path.endswith('/evaluate'):
                raise ValueError('evaluation unavailable')
            return {'status': 'completed', 'result': {'answers': [
                {'id': 'P01-01', 'status': 'ответ', 'answer': '18000'}]}}
        ai_request.side_effect = respond
        with self.assertLogs('chats.comparison_worker', level='ERROR'):
            process_comparison(self.job.id)
        self.job.refresh_from_db()
        self.assertFalse(self.job.result['before']['available'])
        self.assertIsNone(self.job.result['before']['trust_index'])
        self.assertEqual(self.job.result['before']['error']['code'], 'evaluation_failed')
        self.assertEqual(self.client.get(f'/api/comparisons/{self.job.id}/answers.csv?mode=baseline').status_code, 200)


    @patch('chats.comparison_worker.ai_request')
    def test_public_progress_replays_cursor_and_never_exposes_raw_payloads(self, ai_request):
        self.job.progress.update(harness_run_id='harness-run')
        def event(seq, kind, data):
            return {'seq': seq, 'type': kind, 'data': data}
        public = {'title': 'Чтение документа', 'message': 'Документ прочитан', 'status': 'completed',
                  'kind': 'tool', 'details': {'tool': 'read_document'},
                  'private': 'must not be persisted'}
        ai_request.return_value = [
            event(1, 'tool.started', {'arguments': {'text': 'PRIVATE SOURCE'}}),
            event(2, 'llm.started', {'call': 3, 'prompt': 'PRIVATE PROMPT'}),
            event(3, 'harness.step', public),
            event(4, 'harness.step', {'kind': 'result', 'title': 'Результат сохранён'}),
        ]
        run = _read_progress(self.job, self.user.id, 'harness',
                             {'status': 'running', 'metrics': {'model_calls': 0, 'input_tokens': 0}})
        state = _run_state(run)
        self.assertEqual(state['metrics']['model_calls'], 3)
        self.assertFalse(state['metrics_final'])
        self.assertEqual(state['metrics']['input_tokens'], 0)
        self.assertEqual(state['step']['title'], 'Чтение документа')
        self.assertNotIn('PRIVATE', json.dumps(state))
        self.assertNotIn('private', state['step'])
        self.assertEqual(self.job.progress['event_cursors']['harness'], 4)
        self.assertEqual(ai_request.call_args.args[1], '/runs/harness-run/events?after=0&limit=100')
        self.assertEqual(ai_request.call_args.kwargs['user_id'], self.user.id)
        self.job.progress['run_states'] = {'harness': state}
        ai_request.return_value = [event(4, 'llm.started', {'call': 99}),
                                  event(5, 'llm.started', {'call': 4})]
        final = _read_progress(self.job, self.user.id, 'harness',
                              {'status': 'completed', 'metrics': {'model_calls': 4, 'input_tokens': 1200}})
        final_state = _run_state(final)
        self.assertTrue(final_state['metrics_final'])
        self.assertEqual(final_state['model_calls_started'], 4)
        self.assertEqual(final_state['metrics'], {'model_calls': 4, 'input_tokens': 1200})
        self.assertEqual(final_state['step'], state['step'])
        self.assertEqual(ai_request.call_args.args[1], '/runs/harness-run/events?after=4&limit=100')
        self.assertEqual(self.job.progress['event_cursors']['harness'], 5)


    @override_settings(AI_COMPARISON_TIMEOUT_SECONDS=1200)
    @patch('chats.comparison_worker.close_old_connections')
    @patch('chats.comparison_worker.ai_request')
    def test_comparison_timeout_is_frozen_for_both_modes(self, ai_request, close_connections):
        ai_request.side_effect = [{'id': 'baseline'}, {'id': 'harness'}]
        _ensure_run(self.job, self.user.id, 'baseline')
        self.job.refresh_from_db()
        self.assertEqual(self.job.progress['run_timeout_seconds'], 1200)
        self.assertEqual(self.job.progress['wait_timeout_seconds'], 1260)
        with override_settings(AI_COMPARISON_TIMEOUT_SECONDS=1):
            _ensure_run(self.job, self.user.id, 'harness')
        payloads = [call.kwargs['payload'] for call in ai_request.call_args_list]
        self.assertEqual([p['options']['timeout_seconds'] for p in payloads], [1200, 1200])

    @override_settings(AI_COMPARISON_TIMEOUT_SECONDS=1)
    @patch('chats.comparison_worker.close_old_connections')
    @patch('chats.comparison_worker.ai_request')
    def test_comparison_respects_lower_configured_timeout(self, ai_request, close_connections):
        ai_request.return_value = {'id': 'baseline'}
        _ensure_run(self.job, self.user.id, 'baseline')
        self.assertEqual(ai_request.call_args.kwargs['payload']['options']['timeout_seconds'], 1)
        self.assertEqual(self.job.progress['wait_timeout_seconds'], 61)
