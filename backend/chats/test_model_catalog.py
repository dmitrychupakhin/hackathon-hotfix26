import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from chats.model_catalog import CURATED_MODELS
from chats.models import AIModel
from chats.serializers import default_model_id
from users.models import User


class ModelCatalogTests(TestCase):
    def setUp(self):
        AIModel.objects.all().delete()
        for model_id, name in CURATED_MODELS:
            AIModel.objects.create(id=model_id, name=name)

    def test_default_is_luna_instead_of_alphabetically_first_vendor(self):
        with patch.dict(os.environ, {'APIMIRA_MODEL': 'openai/gpt-6-luna'}):
            self.assertEqual(default_model_id(), 'openai/gpt-6-luna')

    def test_configured_default_is_used_when_available(self):
        with patch.dict(os.environ, {'APIMIRA_MODEL': 'deepseek/deepseek-v4-flash'}):
            self.assertEqual(default_model_id(), 'deepseek/deepseek-v4-flash')

    def test_six_options_have_distinct_ids_and_readable_names(self):
        client = APIClient()
        client.force_authenticate(User.objects.create_user('models@example.invalid', 'test-password'))
        with patch.dict(os.environ, {'APIMIRA_MODEL': 'openai/gpt-6-luna'}):
            response = client.get('/api/chats/models')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data[0]['id'], 'openai/gpt-6-luna')
        self.assertEqual({r['id'] for r in response.data}, {r[0] for r in CURATED_MODELS})
        self.assertTrue(all(row['id'] != row['name'] for row in response.data))

    @patch('chats.management.commands.sync_ai_models.ai_request')
    def test_sync_disables_missing_models_but_keeps_custom_display_names(self, request):
        row = AIModel.objects.get(pk='openai/gpt-6-luna')
        row.name = 'Основная модель'
        row.save(update_fields=['name'])
        request.return_value = {
            'provider_configured': True, 'model_catalog_available': True,
            'provider_models': ['openai/gpt-6-luna', 'deepseek/deepseek-v4-flash'],
        }
        call_command('sync_ai_models', stdout=StringIO())
        self.assertEqual(AIModel.objects.filter(is_active=True).count(), 2)
        self.assertEqual(AIModel.objects.get(pk=row.pk).name, 'Основная модель')

    @patch('chats.management.commands.sync_ai_models.ai_request')
    def test_missing_provider_catalog_cannot_disable_working_models(self, request):
        request.return_value = {
            'models': ['openai/gpt-6-luna'], 'provider_configured': False,
            'model_catalog_available': False,
        }
        with self.assertRaises(CommandError):
            call_command('sync_ai_models', stdout=StringIO())
        self.assertEqual(AIModel.objects.filter(is_active=True).count(), 6)
