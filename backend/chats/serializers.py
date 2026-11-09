import hashlib
from pathlib import Path

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import AIModel, Chat, ChatFile, ChatMessage, ChatRun, ComparisonJob

MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024
COMPARISON_DOCUMENT_EXTENSIONS = {
    '.txt', '.md', '.csv', '.json', '.html', '.htm', '.pdf',
    '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg', '.tif',
    '.tiff', '.bmp', '.webp', '.zip',
}


def default_model_id():
    from .model_catalog import available_models
    model_id = available_models().values_list('id', flat=True).first()
    if model_id is None:
        raise serializers.ValidationError({'model_id': ['Нет доступных моделей AI.']})
    return model_id


class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = ('id', 'name')


class ChatSerializer(serializers.ModelSerializer):
    latest_run = serializers.SerializerMethodField()

    @extend_schema_field({"type": "object", "nullable": True, "properties": {
        "id": {"type": "string", "format": "uuid"},
        "status": {"type": "string"}, "error": {"type": "string"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
    }, "required": ["id", "status", "error", "created_at", "updated_at"]})
    def get_latest_run(self, obj):
        run = obj.runs.order_by("-created_at").first()
        return ChatRunSerializer(run).data if run is not None else None

    class Meta:
        model = Chat
        fields = ('id', 'title', 'model_id', 'created_at', 'updated_at', 'latest_run')
        read_only_fields = ('id', 'created_at', 'updated_at', 'latest_run')

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('Название не может быть пустым.')
        return value.strip()

    def validate_model_id(self, value):
        if not AIModel.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError('Модель недоступна.')
        return value

    def validate(self, attrs):
        if self.instance is None and 'model_id' not in attrs:
            attrs['model_id'] = default_model_id()
        return attrs


class SourceLocationSerializer(serializers.Serializer):
    start = serializers.IntegerField()
    end = serializers.IntegerField()
    page = serializers.IntegerField(required=False, allow_null=True)
    sheet = serializers.CharField(required=False, allow_null=True)
    slide = serializers.IntegerField(required=False, allow_null=True)


class CitationSerializer(serializers.Serializer):
    id = serializers.CharField()
    file_id = serializers.UUIDField()
    file_name = serializers.CharField()
    quote = serializers.CharField()
    start = serializers.IntegerField()
    end = serializers.IntegerField()
    text_sha256 = serializers.CharField()
    version = serializers.CharField()
    locations = SourceLocationSerializer(many=True)
    preview_url = serializers.CharField()
    offset_unit = serializers.ChoiceField(choices=['unicode_code_points'])
    anchor_method = serializers.ChoiceField(choices=['harness_evidence', 'exact_text_match'])


class ChatFilePreviewSerializer(serializers.Serializer):
    file_id = serializers.UUIDField()
    name = serializers.CharField()
    format = serializers.ChoiceField(choices=['pdf', 'docx', 'txt', 'md'])
    text = serializers.CharField(allow_blank=True)
    text_sha256 = serializers.CharField()
    original_sha256 = serializers.CharField()
    version = serializers.CharField()
    locations = SourceLocationSerializer(many=True)
    partial = serializers.BooleanField()
    warnings = serializers.ListField(child=serializers.CharField())
    content_url = serializers.CharField()
    offset_unit = serializers.ChoiceField(choices=['unicode_code_points'])


class ChatRunEventSerializer(serializers.Serializer):
    seq = serializers.IntegerField()
    run_id = serializers.CharField()
    type = serializers.CharField()
    data = serializers.DictField()
    created_at = serializers.CharField()


class ChatMessageSerializer(serializers.ModelSerializer):
    content = serializers.CharField(
        max_length=12000, allow_blank=False, trim_whitespace=True,
        help_text='Полное сообщение пользователя. При наличии документов модель выделяет до 50 независимых частей ответа по смыслу (включая CSV/TSV и обычный текст), без разбиения по строкам. Код проверяет сохранение полного текста. Ответ сохраняется одним сообщением с parts; условия общие для всех частей. Планирование входит в общий бюджет запуска.',
    )
    model_id = serializers.CharField(max_length=150, required=False, allow_blank=False)
    citations = CitationSerializer(many=True, read_only=True)
    answer_payload = serializers.JSONField(
        read_only=True,
        help_text='Одиночный AI Answer либо сводный результат: parts[] содержит id, question, status, answer, display_answer, checks, evidence, citation_ids. partial=true означает наличие неопределённых пунктов; проверяйте status каждого parts, а не сводный status. citation_ids ссылаются на верхний citations[].id. Старые сообщения могут содержать {}.',
    )

    class Meta:
        model = ChatMessage
        fields = ('id', 'role', 'content', 'model_id', 'created_at', 'answer_payload', 'citations')
        read_only_fields = ('id', 'role', 'created_at', 'answer_payload', 'citations')

    def validate_model_id(self, value):
        if not AIModel.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError('Модель недоступна.')
        return value


class ChatFileSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, required=True)
    name = serializers.CharField(source='original_name', read_only=True)

    class Meta:
        model = ChatFile
        fields = ('id', 'file', 'name', 'size', 'media_type', 'sha256', 'created_at')
        read_only_fields = ('id', 'name', 'size', 'media_type', 'sha256', 'created_at')

    def validate_file(self, value):
        if value.size > MAX_CHAT_FILE_BYTES:
            raise serializers.ValidationError('Файл не должен превышать 10 МБ.')
        if (not value.name or len(value.name) > 200 or '/' in value.name or '\\' in value.name
                or any(ord(char) < 32 or ord(char) == 127 for char in value.name)):
            raise serializers.ValidationError('Недопустимое имя файла.')
        return value

    def create(self, validated_data):
        uploaded = validated_data.pop('file')
        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        media_type = uploaded.content_type or 'application/octet-stream'
        if len(media_type) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in media_type):
            media_type = 'application/octet-stream'
        return ChatFile.objects.create(
            file=uploaded,
            original_name=uploaded.name,
            size=uploaded.size,
            media_type=media_type,
            sha256=digest.hexdigest(),
            **validated_data,
        )


class FieldErrorsSerializer(serializers.Serializer):
    non_field_errors = serializers.ListField(child=serializers.CharField(), required=False)


class ChatFieldErrorsSerializer(FieldErrorsSerializer):
    title = serializers.ListField(child=serializers.CharField(), required=False)
    model_id = serializers.ListField(child=serializers.CharField(), required=False)


class ChatMessageFieldErrorsSerializer(FieldErrorsSerializer):
    content = serializers.ListField(child=serializers.CharField(), required=False)
    model_id = serializers.ListField(child=serializers.CharField(), required=False)


class ChatFileFieldErrorsSerializer(FieldErrorsSerializer):
    file = serializers.ListField(child=serializers.CharField(), required=False)


class ChatRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRun
        fields = ('id', 'status', 'error', 'created_at', 'updated_at')


class ChatMessageSubmissionSerializer(serializers.Serializer):
    message = ChatMessageSerializer()
    run = ChatRunSerializer()


class ChatRunTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    expires_at = serializers.IntegerField()
    path = serializers.CharField()


class ComparisonCreateSerializer(serializers.Serializer):
    questions = serializers.FileField(help_text='Исходный questions.csv организатора: CSV с сохранением ID, закупок и текста, без обработки моделью.')
    answers = serializers.FileField(help_text='Исходный answers_public.json организатора. Эталоны читает код и не передаёт генерирующей модели.')
    documents = serializers.ListField(child=serializers.FileField(), min_length=1, max_length=64, help_text='Один ZIP с packages/P01…/файлами либо плоские документы только одной закупки. Несколько закупок без папок отклоняются. До 10 МиБ на файл, 32 МиБ суммарно.')
    model_id = serializers.CharField(max_length=150, required=False)

    def validate(self, attrs):
        model_id = attrs.get('model_id') or default_model_id()
        if not AIModel.objects.filter(pk=model_id, is_active=True).exists():
            raise serializers.ValidationError({'model_id': ['Модель недоступна.']})
        attrs['model_id'] = model_id
        for field in ('questions', 'answers'):
            item = attrs[field]
            if not 0 < item.size <= MAX_CHAT_FILE_BYTES:
                raise serializers.ValidationError({field: ['Файл должен быть не больше 10 МБ.']})
            if (not item.name or len(item.name) > 200 or '/' in item.name or '\\' in item.name
                    or any(ord(char) < 32 or ord(char) == 127 for char in item.name)):
                raise serializers.ValidationError({field: ['Недопустимое имя файла.']})
            expected = '.csv' if field == 'questions' else '.json'
            if Path(item.name).suffix.lower() != expected:
                raise serializers.ValidationError({field: [f'Требуется исходный файл {expected}.']})
        documents = attrs['documents']
        if any(not 0 < item.size <= MAX_CHAT_FILE_BYTES for item in documents):
            raise serializers.ValidationError({'documents': ['Каждый документ должен быть не больше 10 МБ.']})
        if sum(item.size for item in documents) > 32 * 1024 * 1024:
            raise serializers.ValidationError({'documents': ['Общий размер документов не должен превышать 32 МБ.']})
        for item in documents:
            if (not item.name or len(item.name) > 200 or '/' in item.name or '\\' in item.name
                    or any(ord(char) < 32 or ord(char) == 127 for char in item.name)):
                raise serializers.ValidationError({'documents': ['Недопустимое имя документа.']})
            if Path(item.name).suffix.lower() not in COMPARISON_DOCUMENT_EXTENSIONS:
                raise serializers.ValidationError({'documents': ['Формат одного из документов не поддерживается AI.']})
        return attrs


class ComparisonDeltaSerializer(serializers.Serializer):
    correct = serializers.FloatField()
    errors = serializers.FloatField()
    careful = serializers.FloatField()
    trust_index = serializers.FloatField()


class ComparisonScoreSerializer(serializers.Serializer):
    available = serializers.BooleanField(default=True)
    status = serializers.CharField(default='completed')
    error = serializers.DictField(allow_null=True, default=None)
    questions = serializers.IntegerField()
    n = serializers.IntegerField(required=False)
    correct = serializers.IntegerField(allow_null=True)
    errors = serializers.IntegerField(allow_null=True)
    careful = serializers.IntegerField(allow_null=True)
    trust_index = serializers.FloatField(allow_null=True)
    by_type = serializers.DictField(required=False)
    rows = serializers.ListField(child=serializers.DictField(), required=False)
    run_metrics = serializers.DictField(required=False)
    prompt_hashes = serializers.DictField(required=False)
    grouping = serializers.CharField(required=False)
    model = serializers.CharField(required=False)


class ComparisonResultSerializer(serializers.Serializer):
    changed_questions = serializers.ListField(child=serializers.DictField())
    before = ComparisonScoreSerializer()
    after = ComparisonScoreSerializer()
    delta = ComparisonDeltaSerializer(allow_null=True)
    warning = serializers.CharField()
    runs = serializers.DictField(required=False)
    protocol = serializers.DictField(required=False)


class ComparisonJobSerializer(serializers.ModelSerializer):
    result = ComparisonResultSerializer(read_only=True, allow_null=True)
    progress = serializers.JSONField(read_only=True, help_text='package_ids: исходный код → AI UUID; run_states: baseline/harness status, metrics, error; question_grouping=per_package. Техническая ошибка отдельного режима не уничтожает результат второго.')

    class Meta:
        model = ComparisonJob
        fields = ('id', 'model_id', 'status', 'stage', 'progress', 'result', 'error', 'created_at', 'updated_at')
        read_only_fields = fields


class ComparisonFieldErrorsSerializer(FieldErrorsSerializer):
    questions = serializers.ListField(child=serializers.CharField(), required=False)
    answers = serializers.ListField(child=serializers.CharField(), required=False)
    documents = serializers.ListField(child=serializers.CharField(), required=False)
    model_id = serializers.ListField(child=serializers.CharField(), required=False)
