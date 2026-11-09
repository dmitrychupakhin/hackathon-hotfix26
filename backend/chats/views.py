import csv
import json
import hashlib
import io
from pathlib import Path
from urllib.parse import urlencode

import requests
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_client import ai_request
from .catalog import register_file, unregister_files
from .models import AIModel, Chat, ChatFile, ChatMessage, ChatRun, ComparisonDocument, ComparisonJob
from .schema import (
    chat_detail_schema,
    chat_file_detail_schema,
    chat_file_download_schema,
    chat_file_preview_schema,
    chat_file_content_schema,
    chat_run_events_schema,
    chat_files_schema,
    chat_list_schema,
    chat_messages_schema,
    chat_models_schema,
    chat_run_cancel_schema,
    chat_run_schema,
    chat_run_ticket_schema,
    comparison_detail_schema,
    comparison_list_schema,
    comparison_answers_schema,
    comparison_report_schema,
)
from .serializers import (
    AIModelSerializer,
    ChatFileSerializer,
    ChatMessageSerializer,
    ChatMessageSubmissionSerializer,
    ChatRunSerializer,
    ChatSerializer,
    ComparisonCreateSerializer,
    ComparisonJobSerializer,
    default_model_id,
)


class ChatPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100


def delete_stored_files(names):
    for name in names:
        default_storage.delete(name)


class OwnedChatMixin:
    def get_chat(self):
        return get_object_or_404(Chat, pk=self.kwargs['chat_id'], owner=self.request.user)


@chat_models_schema
class ChatModelListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AIModelSerializer
    pagination_class = None

    def get_queryset(self):
        from .model_catalog import available_models
        return available_models()


@chat_list_schema
class ChatListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatSerializer
    pagination_class = ChatPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Chat.objects.none()
        return Chat.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@chat_detail_schema
class ChatDetailView(generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ['get', 'patch', 'delete']
    permission_classes = [IsAuthenticated]
    serializer_class = ChatSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Chat.objects.none()
        return Chat.objects.filter(owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = get_object_or_404(Chat.objects.select_for_update(), pk=kwargs['pk'], owner=request.user)
            if instance.runs.filter(status__in=[ChatRun.Status.PENDING, ChatRun.Status.QUEUED, ChatRun.Status.RUNNING]).exists():
                return Response({'detail': ['Сначала отмените текущий ответ AI.']}, status=409)
            self.perform_destroy(instance)
        return Response(status=204)

    def perform_destroy(self, instance):
        attachments = list(instance.files.values_list('id', 'file'))
        with transaction.atomic():
            unregister_files(instance.owner_id, [file_id for file_id, _ in attachments])
            instance.delete()
            transaction.on_commit(lambda: delete_stored_files([name for _, name in attachments]))


@chat_messages_schema
class ChatMessageListCreateView(OwnedChatMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatMessageSerializer
    pagination_class = ChatPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChatMessage.objects.none()
        return self.get_chat().messages.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            chat = get_object_or_404(Chat.objects.select_for_update(), pk=self.kwargs['chat_id'], owner=request.user)
            if chat.runs.filter(status__in=[ChatRun.Status.PENDING, ChatRun.Status.QUEUED, ChatRun.Status.RUNNING]).exists():
                return Response({'detail': ['Дождитесь завершения текущего ответа.']}, status=409)
            model_id = serializer.validated_data.get('model_id') or chat.model_id or default_model_id()
            if not AIModel.objects.filter(id=model_id, is_active=True).exists():
                raise ValidationError({'model_id': ['Модель недоступна.']})
            chat.model_id = model_id
            history_ids = list(chat.messages.order_by('-created_at', '-id').values_list('id', flat=True)[:20])
            history_ids.reverse()
            file_ids = list(chat.files.values_list('id', flat=True))
            message = serializer.save(chat=chat, role=ChatMessage.Role.USER, model_id=model_id)
            run = ChatRun.objects.create(
                chat=chat,
                user_message=message,
                input_snapshot={
                    'history_ids': [str(item) for item in history_ids],
                    'file_ids': [str(item) for item in file_ids],
                    'system_prompt': request.user.system_prompt,
                },
            )
            chat.save(update_fields=['model_id', 'updated_at'])
        return Response(
            ChatMessageSubmissionSerializer({'message': message, 'run': run}).data,
            status=status.HTTP_202_ACCEPTED,
        )


@chat_files_schema
class ChatFileListCreateView(OwnedChatMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]
    serializer_class = ChatFileSerializer
    pagination_class = ChatPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChatFile.objects.none()
        return self.get_chat().files.all()

    def create(self, request, *args, **kwargs):
        if len(request.FILES.getlist('file')) > 1 or len(request.FILES) > 1:
            return Response({'file': ['За один запрос можно загрузить только один файл.']}, status=400)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        attachment = None
        try:
            with transaction.atomic():
                chat = get_object_or_404(Chat.objects.select_for_update(), pk=self.kwargs['chat_id'], owner=self.request.user)
                if chat.files.count() >= 64:
                    raise ValidationError({'file': ['К чату можно прикрепить не более 64 файлов.']})
                attachment = serializer.save(chat=chat)
                register_file(attachment, chat.owner_id)
                chat.save(update_fields=['updated_at'])
        except Exception:
            if attachment is not None:
                attachment.file.delete(save=False)
            raise


class OwnedChatFileMixin:
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChatFile.objects.none()
        return ChatFile.objects.filter(
            chat_id=self.kwargs['chat_id'],
            chat__owner=self.request.user,
        )


@chat_file_detail_schema
class ChatFileDetailView(OwnedChatFileMixin, generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatFileSerializer

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            chat = get_object_or_404(Chat.objects.select_for_update(), pk=kwargs['chat_id'], owner=request.user)
            instance = get_object_or_404(ChatFile, pk=kwargs['pk'], chat=chat)
            if chat.runs.filter(status__in=[ChatRun.Status.PENDING, ChatRun.Status.QUEUED, ChatRun.Status.RUNNING]).exists():
                return Response({'detail': ['Сначала отмените текущий ответ AI.']}, status=409)
            self.perform_destroy(instance)
        return Response(status=204)

    def perform_destroy(self, instance):
        chat = instance.chat
        name = instance.file.name
        with transaction.atomic():
            unregister_files(chat.owner_id, [instance.id])
            instance.delete()
            chat.save(update_fields=['updated_at'])
            transaction.on_commit(lambda: default_storage.delete(name))


@chat_file_download_schema
class ChatFileDownloadView(OwnedChatFileMixin, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatFileSerializer

    def get(self, request, *args, **kwargs):
        attachment = self.get_object()
        try:
            source = attachment.file.open('rb')
        except FileNotFoundError:
            raise Http404('Файл не найден.') from None
        return FileResponse(
            source,
            as_attachment=True,
            filename=attachment.original_name,
            content_type='application/octet-stream',
        )


def file_preview_data(attachment, owner_id, query):
    params = {}
    if 'text_sha256' in query:
        import re
        if not re.fullmatch(r'[a-f0-9]{64}', query['text_sha256']):
            raise ValidationError({'text_sha256': ['Ожидается SHA-256 текста.']})
        params['text_sha256'] = query['text_sha256']
    if 'version' in query:
        if not query['version'] or len(query['version']) > 128:
            raise ValidationError({'version': ['Недопустимая версия документа.']})
        params['version'] = query['version']
    suffix = '?' + urlencode(params) if params else ''
    try:
        data = ai_request('GET', f'/files/{attachment.id}/preview{suffix}', user_id=owner_id, timeout=320)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 502
        if code == 409:
            return None, Response({'detail': ['Документ изменился. Цитата относится к другой версии текста.']}, status=409)
        if code in (404, 413, 422):
            return None, Response({'detail': ['Предпросмотр этого документа недоступен.']}, status=code)
        return None, Response({'detail': ['AI-сервис недоступен.']}, status=502)
    except (requests.RequestException, RuntimeError, ValueError):
        return None, Response({'detail': ['AI-сервис недоступен.']}, status=502)
    if (data.get('file_id') != str(attachment.id)
            or data.get('original_sha256') != attachment.sha256
            or data.get('version') != attachment.sha256):
        return None, Response({'detail': ['Версия документа изменилась.']}, status=409)
    data['name'] = attachment.original_name
    data['content_url'] = f'/api/chats/{attachment.chat_id}/files/{attachment.id}/content'
    return data, None


@chat_file_preview_schema
class ChatFilePreviewView(OwnedChatFileMixin, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatFileSerializer

    def get(self, request, *args, **kwargs):
        data, error = file_preview_data(self.get_object(), request.user.pk, request.query_params)
        return error if error is not None else Response(data)


@chat_file_content_schema
class ChatFileContentView(OwnedChatFileMixin, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatFileSerializer

    def get(self, request, *args, **kwargs):
        attachment = self.get_object()
        suffix = Path(attachment.original_name).suffix.lower()
        if suffix in {'.pdf', '.docx'}:
            if 'version' in request.query_params or 'text_sha256' in request.query_params:
                _, error = file_preview_data(attachment, request.user.pk, request.query_params)
                if error is not None:
                    return error
            try:
                with attachment.file.open('rb') as source:
                    raw = source.read(10 * 1024 * 1024 + 1)
            except FileNotFoundError:
                raise Http404('Файл не найден.') from None
            if len(raw) > 10 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != attachment.sha256:
                return Response({'detail': ['Исходный файл изменился.']}, status=409)
            mime = 'application/pdf' if suffix == '.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            response = FileResponse(io.BytesIO(raw), as_attachment=False, filename=attachment.original_name, content_type=mime)
        else:
            data, error = file_preview_data(attachment, request.user.pk, request.query_params)
            if error is not None:
                return error
            response = FileResponse(io.BytesIO(data['text'].encode('utf-8')), as_attachment=False,
                                    filename=Path(attachment.original_name).stem + '.txt',
                                    content_type='text/plain; charset=utf-8')
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        response['Content-Security-Policy'] = "sandbox"
        return response


@chat_run_events_schema
class ChatRunEventsView(OwnedChatMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, chat_id, pk):
        run = get_object_or_404(ChatRun, pk=pk, chat=self.get_chat())
        try:
            after = int(request.query_params.get('after', 0))
            limit = int(request.query_params.get('limit', 100))
        except (TypeError, ValueError):
            raise ValidationError({'detail': ['after и limit должны быть целыми числами.']}) from None
        if after < 0 or not 1 <= limit <= 500:
            raise ValidationError({'detail': ['after >= 0; limit от 1 до 500.']})
        if not run.ai_run_id:
            return Response([])
        try:
            data = ai_request('GET', f'/runs/{run.ai_run_id}/events?after={after}&limit={limit}', user_id=request.user.pk)
        except (requests.RequestException, RuntimeError, ValueError):
            return Response({'detail': ['AI-сервис недоступен.']}, status=502)
        return Response(data)


@chat_run_schema
class ChatRunDetailView(OwnedChatMixin, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatRunSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChatRun.objects.none()
        return ChatRun.objects.filter(chat=self.get_chat())


@chat_run_ticket_schema
class ChatRunTicketView(OwnedChatMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, chat_id, pk):
        run = get_object_or_404(ChatRun, pk=pk, chat=self.get_chat())
        if not run.ai_run_id:
            return Response({'detail': ['Запуск AI ещё не начался.']}, status=409)
        try:
            ticket = ai_request('POST', f'/runs/{run.ai_run_id}/ws-ticket', user_id=request.user.pk)
        except (requests.RequestException, RuntimeError, ValueError):
            return Response({'detail': ['AI-сервис недоступен.']}, status=502)
        ticket['path'] = '/ai' + ticket['path']
        return Response(ticket)


@chat_run_cancel_schema
class ChatRunCancelView(OwnedChatMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, chat_id, pk):
        run = get_object_or_404(ChatRun, pk=pk, chat=self.get_chat())
        if run.status == ChatRun.Status.PENDING:
            run.status = ChatRun.Status.CANCELLED
            run.save(update_fields=['status', 'updated_at'])
        elif run.status in (ChatRun.Status.QUEUED, ChatRun.Status.RUNNING):
            try:
                ai_request('POST', f'/runs/{run.ai_run_id}/cancel', user_id=request.user.pk)
            except (requests.RequestException, RuntimeError, ValueError):
                return Response({'detail': ['AI-сервис недоступен.']}, status=502)
        return Response(ChatRunSerializer(run).data)


@comparison_list_schema
class ComparisonListCreateView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ComparisonJobSerializer
    pagination_class = ChatPagination
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ComparisonJob.objects.none()
        return ComparisonJob.objects.filter(owner=self.request.user)

    def post(self, request, *args, **kwargs):
        serializer = ComparisonCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stored_files = []
        try:
            with transaction.atomic():
                job = ComparisonJob.objects.create(
                    owner=request.user,
                    model_id=data['model_id'],
                    system_prompt=request.user.system_prompt,
                )
                uploads = [
                    (ComparisonDocument.Kind.QUESTIONS, data['questions']),
                    (ComparisonDocument.Kind.ANSWERS, data['answers']),
                    *((ComparisonDocument.Kind.DOCUMENT, upload) for upload in data['documents']),
                ]
                for kind, upload in uploads:
                    digest = hashlib.sha256()
                    for chunk in upload.chunks():
                        digest.update(chunk)
                    upload.seek(0)
                    media_type = upload.content_type or 'application/octet-stream'
                    if len(media_type) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in media_type):
                        media_type = 'application/octet-stream'
                    document = ComparisonDocument(
                        comparison=job,
                        kind=kind,
                        original_name=upload.name,
                        size=upload.size,
                        media_type=media_type,
                        sha256=digest.hexdigest(),
                    )
                    document.file.save(upload.name, upload, save=False)
                    stored_files.append(document.file.name)
                    document.save()
                    register_file(document, request.user.pk)
        except Exception:
            delete_stored_files(stored_files)
            raise
        return Response(ComparisonJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


@comparison_detail_schema
class ComparisonDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ComparisonJobSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ComparisonJob.objects.none()
        return ComparisonJob.objects.filter(owner=self.request.user)


@comparison_answers_schema
class ComparisonAnswersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = get_object_or_404(ComparisonJob, pk=pk, owner=request.user)
        mode = request.query_params.get('mode')
        if mode not in ('baseline', 'harness'):
            return Response({'detail': ['mode должен быть baseline или harness.']}, status=400)
        run = (job.result or {}).get('runs', {}).get(mode)
        if not run or run.get('status') != 'completed':
            return Response({'detail': ['Завершённые ответы этого режима недоступны.']}, status=409)
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=['id', 'status', 'answer', 'quote', 'file'],
                                delimiter=';', lineterminator='\n')
        writer.writeheader()
        for answer in run.get('answers', []):
            writer.writerow({key: ' '.join(str(answer.get(key) or '').splitlines())
                             for key in writer.fieldnames})
        response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="answers-{mode}.csv"'
        response['Cache-Control'] = 'private, no-store'
        return response


@comparison_report_schema
class ComparisonReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        job = get_object_or_404(ComparisonJob, pk=pk, owner=request.user)
        if job.result is None:
            return Response({'detail': ['Отчёт ещё не сформирован.']}, status=409)
        report = {'id': str(job.id), 'model': job.model_id, 'status': job.status,
                  'profile_instructions': job.system_prompt,
                  'created_at': job.created_at.isoformat(), 'updated_at': job.updated_at.isoformat(),
                  'questions': job.questions, 'reference_answers': job.reference_answers,
                  'result': job.result}
        response = HttpResponse(json.dumps(report, ensure_ascii=False, indent=2),
                                content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="comparison-report.json"'
        response['Cache-Control'] = 'private, no-store'
        return response
