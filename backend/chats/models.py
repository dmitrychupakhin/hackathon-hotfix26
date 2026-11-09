from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models

from utils.mixins import TimeStampedMixin


def chat_file_path(instance, filename):
    suffix = Path(filename.replace('\\', '/')).suffix.lower()[:20]
    return f'chats/{instance.chat_id}/{uuid4().hex}{suffix}'


def comparison_file_path(instance, filename):
    suffix = Path(filename.replace('\\', '/')).suffix.lower()[:20]
    return f'comparisons/{instance.comparison_id}/{uuid4().hex}{suffix}'


class Chat(TimeStampedMixin):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chats')
    title = models.CharField(max_length=200, default='Новый чат')
    model_id = models.CharField(max_length=150, blank=True, default='')

    class Meta:
        ordering = ['-updated_at', '-created_at']


class AIModel(models.Model):
    id = models.CharField(max_length=150, primary_key=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'Пользователь'
        ASSISTANT = 'assistant', 'Ассистент'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    answer_payload = models.JSONField(default=dict, blank=True)
    citations = models.JSONField(default=list, blank=True)
    model_id = models.CharField(max_length=150, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class ChatFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=chat_file_path, max_length=500)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    media_type = models.CharField(max_length=255, default='application/octet-stream')
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class ChatRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает отправки'
        QUEUED = 'queued', 'В очереди'
        RUNNING = 'running', 'Выполняется'
        COMPLETED = 'completed', 'Завершён'
        FAILED = 'failed', 'Ошибка'
        CANCELLED = 'cancelled', 'Отменён'
        INTERRUPTED = 'interrupted', 'Прерван'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='runs')
    user_message = models.OneToOneField(ChatMessage, on_delete=models.CASCADE, related_name='run')
    assistant_message = models.OneToOneField(
        ChatMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name='answer_run'
    )
    ai_run_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    input_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class ComparisonJob(TimeStampedMixin):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает запуска'
        RUNNING = 'running', 'Выполняется'
        COMPLETED = 'completed', 'Завершено'
        FAILED = 'failed', 'Ошибка'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comparisons')
    model_id = models.CharField(max_length=150)
    questions = models.JSONField(default=list)
    reference_answers = models.JSONField(default=list)
    system_prompt = models.TextField(blank=True, default='')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    stage = models.CharField(max_length=32, default='pending')
    progress = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']


class ComparisonDocument(models.Model):
    class Kind(models.TextChoices):
        QUESTIONS = 'questions', 'Вопросы'
        ANSWERS = 'answers', 'Ответы'
        DOCUMENT = 'document', 'Документ'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    comparison = models.ForeignKey(ComparisonJob, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.DOCUMENT)
    file = models.FileField(upload_to=comparison_file_path, max_length=500)
    original_name = models.CharField(max_length=200)
    size = models.PositiveBigIntegerField()
    media_type = models.CharField(max_length=200, default='application/octet-stream')
    sha256 = models.CharField(max_length=64)

    class Meta:
        ordering = ['id']
