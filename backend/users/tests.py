from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from .instructions import DEFAULT_AI_INSTRUCTIONS
from .models import User


class DefaultInstructionsTests(TestCase):
    def test_new_user_sees_default_and_can_replace_it_without_affecting_others(self):
        user = User.objects.create_user('instructions@example.invalid', 'test-password')
        other = User.objects.create_user('other-instructions@example.invalid', 'test-password')
        self.assertEqual(user.system_prompt, DEFAULT_AI_INSTRUCTIONS)
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get('/api/users/me').data['system_prompt'], DEFAULT_AI_INSTRUCTIONS)
        response = client.patch('/api/users/me', {'system_prompt': 'Мои инструкции'}, format='json')
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(user.system_prompt, 'Мои инструкции')
        self.assertEqual(other.system_prompt, DEFAULT_AI_INSTRUCTIONS)

    def test_migration_fills_only_blank_profiles(self):
        blank = User.objects.create_user('blank@example.invalid', 'test-password', system_prompt='')
        whitespace = User.objects.create_user('spaces@example.invalid', 'test-password', system_prompt=' \n ')
        custom = User.objects.create_user('custom@example.invalid', 'test-password', system_prompt='Собственный текст')
        migration = import_module('users.migrations.0004_default_ai_instructions')
        migration.fill_empty_instructions(apps, SimpleNamespace(connection=connection))
        for user in (blank, whitespace, custom):
            user.refresh_from_db()
        self.assertEqual(blank.system_prompt, DEFAULT_AI_INSTRUCTIONS)
        self.assertEqual(whitespace.system_prompt, DEFAULT_AI_INSTRUCTIONS)
        self.assertEqual(custom.system_prompt, 'Собственный текст')
