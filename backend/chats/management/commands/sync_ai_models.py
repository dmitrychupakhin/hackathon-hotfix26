import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chats.ai_client import ai_request
from chats.model_catalog import CURATED_MODELS
from chats.models import AIModel


class Command(BaseCommand):
    help = 'Сверяет шесть моделей каталога с AI-провайдером без платных генераций.'

    def handle(self, *args, **options):
        try:
            info = ai_request('GET', '/info')
            ids = info.get('provider_models')
            if not isinstance(ids, list) or not ids or not all(isinstance(value, str) for value in ids):
                raise ValueError('Invalid model catalogue')
            # A missing API key only exposes the configured fallback model. Do not
            # disable working models based on this incomplete metadata response.
            if not info.get('provider_configured') or not info.get('model_catalog_available'):
                raise ValueError('AI provider is not configured or its catalogue is unavailable')
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            raise CommandError('Не удалось прочитать каталог AI. Существующие модели не изменены.') from exc
        with transaction.atomic():
            for model_id, name in CURATED_MODELS:
                row, _ = AIModel.objects.get_or_create(pk=model_id, defaults={'name': name})
                row.is_active = model_id in ids
                if row.name in ('', model_id):
                    row.name = name
                row.save(update_fields=['name', 'is_active'])
                self.stdout.write(f'{model_id}: {"доступна" if row.is_active else "недоступна"}')
