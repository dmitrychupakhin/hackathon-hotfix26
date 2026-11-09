from django.db import migrations


def seed_models(apps, schema_editor):
    model = apps.get_model('chats', 'AIModel')
    models = (
        ('openai/gpt-6-luna', 'GPT-6 Luna · OpenAI'),
        ('openai/gpt-6-astra', 'GPT-6 Astra · OpenAI'),
        ('openai/gpt-5.4-mini', 'GPT-5.4 Mini · OpenAI'),
        ('anthropic/claude-sonnet-4.6', 'Claude Sonnet 4.6 · Anthropic'),
        ('google/gemini-3-flash-preview', 'Gemini 3 Flash Preview · Google'),
        ('deepseek/deepseek-v4-flash', 'DeepSeek V4 Flash · DeepSeek'),
    )
    for model_id, name in models:
        row, created = model.objects.using(schema_editor.connection.alias).get_or_create(
            pk=model_id, defaults={'name': name, 'is_active': True},
        )
        if not created and row.name in ('', model_id):
            row.name = name
            row.save(update_fields=['name'], using=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [('chats', '0005_message_evidence')]
    operations = [migrations.RunPython(seed_models, migrations.RunPython.noop)]
