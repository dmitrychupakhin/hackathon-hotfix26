import chats.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chats', '0003_ai_storage'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ComparisonJob',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('model_id', models.CharField(max_length=150)),
                ('questions', models.JSONField(default=list)),
                ('reference_answers', models.JSONField(default=list)),
                ('system_prompt', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[
                    ('pending', 'Ожидает запуска'), ('running', 'Выполняется'),
                    ('completed', 'Завершено'), ('failed', 'Ошибка'),
                ], default='pending', max_length=16)),
                ('stage', models.CharField(default='pending', max_length=32)),
                ('progress', models.JSONField(default=dict)),
                ('result', models.JSONField(blank=True, null=True)),
                ('error', models.TextField(blank=True, default='')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='comparisons', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ComparisonDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('questions', 'Вопросы'), ('answers', 'Ответы'), ('document', 'Документ')], default='document', max_length=16)),
                ('file', models.FileField(max_length=500, upload_to=chats.models.comparison_file_path)),
                ('original_name', models.CharField(max_length=200)),
                ('size', models.PositiveBigIntegerField()),
                ('media_type', models.CharField(default='application/octet-stream', max_length=200)),
                ('sha256', models.CharField(max_length=64)),
                ('comparison', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                 related_name='documents', to='chats.comparisonjob')),
            ],
            options={'ordering': ['id']},
        ),
    ]
