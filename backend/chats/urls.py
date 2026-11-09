from django.urls import path

from .views import (
    ChatDetailView,
    ChatFileDetailView,
    ChatFileDownloadView,
    ChatFilePreviewView,
    ChatFileContentView,
    ChatRunEventsView,
    ChatFileListCreateView,
    ChatListCreateView,
    ChatMessageListCreateView,
    ChatModelListView,
    ChatRunCancelView,
    ChatRunDetailView,
    ChatRunTicketView,
    ComparisonDetailView,
    ComparisonAnswersView,
    ComparisonReportView,
    ComparisonListCreateView,
)


urlpatterns = [
    path('chats/models', ChatModelListView.as_view()),
    path('chats', ChatListCreateView.as_view()),
    path('chats/<uuid:pk>', ChatDetailView.as_view()),
    path('chats/<uuid:chat_id>/messages', ChatMessageListCreateView.as_view()),
    path('chats/<uuid:chat_id>/runs/<uuid:pk>', ChatRunDetailView.as_view()),
    path('chats/<uuid:chat_id>/runs/<uuid:pk>/events', ChatRunEventsView.as_view()),
    path('chats/<uuid:chat_id>/runs/<uuid:pk>/ws-ticket', ChatRunTicketView.as_view()),
    path('chats/<uuid:chat_id>/runs/<uuid:pk>/cancel', ChatRunCancelView.as_view()),
    path('chats/<uuid:chat_id>/files', ChatFileListCreateView.as_view()),
    path('chats/<uuid:chat_id>/files/<uuid:pk>', ChatFileDetailView.as_view()),
    path('chats/<uuid:chat_id>/files/<uuid:pk>/download', ChatFileDownloadView.as_view()),
    path('chats/<uuid:chat_id>/files/<uuid:pk>/preview', ChatFilePreviewView.as_view()),
    path('chats/<uuid:chat_id>/files/<uuid:pk>/content', ChatFileContentView.as_view()),
    path('comparisons', ComparisonListCreateView.as_view()),
    path('comparisons/<uuid:pk>', ComparisonDetailView.as_view()),
    path('comparisons/<uuid:pk>/answers.csv', ComparisonAnswersView.as_view()),
    path('comparisons/<uuid:pk>/report.json', ComparisonReportView.as_view()),
]
