"""A small operator-owned model catalogue; API model IDs stay separate from UI names."""

import os

from django.db.models import Case, IntegerField, Value, When

CURATED_MODELS = (
    ('openai/gpt-6-luna', 'GPT-6 Luna · OpenAI'),
    ('openai/gpt-6-astra', 'GPT-6 Astra · OpenAI'),
    ('openai/gpt-5.4-mini', 'GPT-5.4 Mini · OpenAI'),
    ('anthropic/claude-sonnet-4.6', 'Claude Sonnet 4.6 · Anthropic'),
    ('google/gemini-3-flash-preview', 'Gemini 3 Flash Preview · Google'),
    ('deepseek/deepseek-v4-flash', 'DeepSeek V4 Flash · DeepSeek'),
)


def configured_default_model():
    return os.environ.get('APIMIRA_MODEL') or 'openai/gpt-6-luna'


def available_models():
    from .models import AIModel

    # The provider ID in a request is never derived from the human-readable name.
    return AIModel.objects.filter(is_active=True).annotate(
        default_priority=Case(
            When(pk=configured_default_model(), then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        )
    ).order_by('default_priority', 'name', 'id')
