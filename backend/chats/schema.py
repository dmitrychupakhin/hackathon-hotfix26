from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    PolymorphicProxySerializer,
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)

from users.serializers import DetailListSerializer

from .serializers import (
    AIModelSerializer,
    ChatFieldErrorsSerializer,
    ChatFileFieldErrorsSerializer,
    ChatFileSerializer,
    ChatFilePreviewSerializer,
    ChatRunEventSerializer,
    ChatMessageFieldErrorsSerializer,
    ChatMessageSerializer,
    ChatMessageSubmissionSerializer,
    ChatRunSerializer,
    ChatRunTicketSerializer,
    ChatSerializer,
    ComparisonCreateSerializer,
    ComparisonFieldErrorsSerializer,
    ComparisonJobSerializer,
)

chat_list_schema = extend_schema_view(
    get=extend_schema(
        summary='Список чатов',
        tags=['Чаты'],
        responses={200: ChatSerializer(many=True), 401: DetailListSerializer},
    ),
    post=extend_schema(
        summary='Создать чат',
        tags=['Чаты'],
        request=ChatSerializer,
        responses={
            201: ChatSerializer,
            400: PolymorphicProxySerializer(
                component_name='CreateChatError',
                serializers=[DetailListSerializer, ChatFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
        },
    ),
)


chat_detail_schema = extend_schema_view(
    get=extend_schema(
        summary='Получить чат',
        tags=['Чаты'],
        responses={200: ChatSerializer, 401: DetailListSerializer, 404: DetailListSerializer},
    ),
    patch=extend_schema(
        summary='Изменить название или модель чата',
        tags=['Чаты'],
        request=ChatSerializer,
        responses={
            200: ChatSerializer,
            400: PolymorphicProxySerializer(
                component_name='UpdateChatError',
                serializers=[DetailListSerializer, ChatFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
            404: DetailListSerializer,
        },
    ),
    delete=extend_schema(
        summary='Удалить чат',
        tags=['Чаты'],
        responses={204: None, 401: DetailListSerializer, 404: DetailListSerializer,
                   409: DetailListSerializer},
    ),
)


chat_messages_schema = extend_schema_view(
    get=extend_schema(
        summary='История сообщений чата',
        tags=['Чаты'],
        responses={
            200: ChatMessageSerializer(many=True),
            401: DetailListSerializer,
            404: DetailListSerializer,
        },
    ),
    post=extend_schema(
        summary='Отправить сообщение в AI',
        tags=['Чаты'],
        request=ChatMessageSerializer,
        responses={
            202: ChatMessageSubmissionSerializer,
            400: PolymorphicProxySerializer(
                component_name='CreateChatMessageError',
                serializers=[DetailListSerializer, ChatMessageFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
            404: DetailListSerializer,
            409: DetailListSerializer,
        },
    ),
)


chat_files_schema = extend_schema_view(
    get=extend_schema(
        summary='Файлы чата',
        tags=['Чаты'],
        responses={
            200: ChatFileSerializer(many=True),
            401: DetailListSerializer,
            404: DetailListSerializer,
        },
    ),
    post=extend_schema(
        summary='Загрузить один файл в чат',
        tags=['Чаты'],
        request=ChatFileSerializer,
        responses={
            201: ChatFileSerializer,
            400: PolymorphicProxySerializer(
                component_name='UploadChatFileError',
                serializers=[DetailListSerializer, ChatFileFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
            404: DetailListSerializer,
        },
    ),
)


chat_file_detail_schema = extend_schema_view(
    get=extend_schema(
        summary='Информация о файле чата',
        tags=['Чаты'],
        responses={200: ChatFileSerializer, 401: DetailListSerializer, 404: DetailListSerializer},
    ),
    delete=extend_schema(
        summary='Удалить файл из чата',
        tags=['Чаты'],
        responses={204: None, 401: DetailListSerializer, 404: DetailListSerializer,
                   409: DetailListSerializer},
    ),
)


chat_file_download_schema = extend_schema_view(get=extend_schema(
    summary='Скачать файл чата',
    tags=['Чаты'],
    responses={
        (200, 'application/octet-stream'): OpenApiTypes.BINARY,
        401: DetailListSerializer,
        404: DetailListSerializer,
    },
))


chat_models_schema = extend_schema(
    summary='Доступные модели AI', tags=['Чаты'],
    responses={200: AIModelSerializer(many=True), 401: DetailListSerializer},
)


chat_run_schema = extend_schema(
    summary='Состояние ответа AI', tags=['Чаты'],
    responses={200: ChatRunSerializer, 401: DetailListSerializer, 404: DetailListSerializer},
)


chat_run_ticket_schema = extend_schema(
    summary='Билет для WebSocket событий AI', tags=['Чаты'],
    request=None,
    responses={200: ChatRunTicketSerializer, 401: DetailListSerializer,
               404: DetailListSerializer, 409: DetailListSerializer, 502: DetailListSerializer},
)


chat_run_cancel_schema = extend_schema(
    summary='Отменить ответ AI', tags=['Чаты'], request=None,
    responses={200: ChatRunSerializer, 401: DetailListSerializer,
               404: DetailListSerializer, 502: DetailListSerializer},
)


comparison_list_schema = extend_schema_view(
    get=extend_schema(
        summary='Список сравнений', tags=['Сравнения'],
        responses={200: ComparisonJobSerializer(many=True), 401: DetailListSerializer},
    ),
    post=extend_schema(
        summary='Загрузить вопросы, эталоны и документы для сравнения режимов AI',
        tags=['Сравнения'],
        request=ComparisonCreateSerializer,
        responses={
            202: ComparisonJobSerializer,
            400: PolymorphicProxySerializer(
                component_name='CreateComparisonError',
                serializers=[DetailListSerializer, ComparisonFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
        },
    ),
)


comparison_detail_schema = extend_schema(
    summary='Статус и результат сравнения', tags=['Сравнения'],
    responses={200: ComparisonJobSerializer, 401: DetailListSerializer, 404: DetailListSerializer},
)


chat_file_preview_schema = extend_schema_view(get=extend_schema(
    summary='Предпросмотр документа и точный текст для перехода к цитате',
    description='Координаты цитат: Unicode code points, end не включается. При несовпадении text_sha256/version возвращается 409. Только файлы своего чата.',
    tags=['Чаты'],
    parameters=[OpenApiParameter('text_sha256', str, description='Ожидаемый SHA-256 извлечённого текста'),
                OpenApiParameter('version', str, description='Версия источника из цитаты')],
    responses={200: ChatFilePreviewSerializer, 400: DetailListSerializer, 401: DetailListSerializer,
               404: DetailListSerializer, 409: DetailListSerializer, 413: DetailListSerializer,
               422: DetailListSerializer, 502: DetailListSerializer},
))

chat_file_content_schema = extend_schema_view(get=extend_schema(
    summary='Оригинал PDF/DOCX для предпросмотра; остальные форматы — извлечённый TXT',
    description='Требуется обычная авторизация. Получите Blob через fetch с токеном; токен в URL не передавать. Content-Disposition: inline, Cache-Control: private, no-store.',
    tags=['Чаты'],
    responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY,
               401: DetailListSerializer, 404: DetailListSerializer, 409: DetailListSerializer,
               413: DetailListSerializer, 422: DetailListSerializer, 502: DetailListSerializer},
))

chat_run_events_schema = extend_schema_view(get=extend_schema(
    summary='Повтор событий запуска; HTTP-резерв для WebSocket',
    tags=['Чаты'],
    parameters=[OpenApiParameter('after', int, description='Последний обработанный seq, от 0'),
                OpenApiParameter('limit', int, description='Размер порции: 1–500, по умолчанию 100')],
    responses={200: ChatRunEventSerializer(many=True), 400: DetailListSerializer,
               401: DetailListSerializer, 404: DetailListSerializer, 502: DetailListSerializer},
))


comparison_answers_schema = extend_schema_view(get=extend_schema(
    operation_id='comparisons_answers_retrieve',
    summary='Скачать answers.csv отдельного режима', tags=['Сравнения'],
    description='UTF-8, разделитель ;, колонки id;status;answer;quote;file. Только завершённый режим своего сравнения; технический отказ не заменяется ответами «не знаю».',
    parameters=[OpenApiParameter('mode', str, required=True, enum=['baseline', 'harness'])],
    responses={(200, 'text/csv'): OpenApiTypes.BINARY, 400: DetailListSerializer,
               401: DetailListSerializer, 404: DetailListSerializer, 409: DetailListSerializer},
))

comparison_report_schema = extend_schema_view(get=extend_schema(
    operation_id='comparisons_report_retrieve',
    summary='Скачать JSON отчёт сравнения', tags=['Сравнения'],
    description='Оригинальные вопросы/эталоны, protocol, независимые оценки before/after, ответы и цитаты, проверки, метрики и хеши. Для воспроизводимости включены зафиксированные инструкции профиля и snapshot промптов завершённых оценок. Ключи провайдера/сервиса не включаются. Только своё сравнение.',
    responses={(200, 'application/json'): OpenApiTypes.BINARY, 401: DetailListSerializer,
               404: DetailListSerializer, 409: DetailListSerializer},
))
