from django.urls import path

from .views import (
    ConfirmRegisterView,
    ConfirmResetPasswordView,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    LogoutView,
    RegisterView,
    ResetPasswordView,
    UpdateEmailConfirmView,
    UpdateEmailView,
    UpdatePasswordView,
    UserPhotoUpdateView,
    UserRetrieveView,
    UserRetrieveUpdateView,
    VKAuthView,
)

urlpatterns = [
    path('users/register', RegisterView.as_view()),
    path('users/register/confirm', ConfirmRegisterView.as_view()),

    path('users/login', CookieTokenObtainPairView.as_view()),
    path('users/logout', LogoutView.as_view()),
    path('users/refresh', CookieTokenRefreshView.as_view()),

    path('users/vk/login', VKAuthView.as_view()),

    path('users/<int:pk>', UserRetrieveView.as_view()),

    path('users/me', UserRetrieveUpdateView.as_view()),
    path('users/me/photo', UserPhotoUpdateView.as_view()),
    path('users/email', UpdateEmailView.as_view()),
    path('users/email/confirm', UpdateEmailConfirmView.as_view()),
    path('users/password', UpdatePasswordView.as_view()),
    path('users/password/reset', ResetPasswordView.as_view()),
    path('users/password/reset/confirm', ConfirmResetPasswordView.as_view()),
]
