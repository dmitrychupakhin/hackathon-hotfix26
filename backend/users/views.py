import random

from django.conf import settings
from django.core.cache import cache
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from services import vk
from utils.cookies import set_auth_cookies
from utils.password import gen_password
from services.mailer import send_email

from .models import User
from .schema import (
    confirm_register_schema,
    confirm_reset_password_schema,
    confirm_update_email_schema,
    login_schema,
    logout_schema,
    refresh_schema,
    register_schema,
    reset_password_schema,
    update_email_schema,
    update_password_schema,
    update_photo_schema,
    user_profile_schema,
    user_retrieve_schema,
    vk_auth_schema,
)
from .serializers import (
    ConfirmRegisterSerializer,
    CustomTokenObtainPairSerializer,
    EmailSerializer,
    EmailWithCodeSerializer,
    MeSerializer,
    NewEmailSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UpdatePasswordSerializer,
    UpdatePhotoSerializer,
    UpdateSerializer,
    UserSerializer,
    VKAuthSerializer,
)


@register_schema
class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        User.objects.filter(email=email, is_active=False).delete()
        cache.delete(f"register_code:{email}")

        user = User.objects.create_user(
            email=email,
            password=serializer.validated_data['password'],
            is_active=False,
        )

        code = str(random.randint(100000, 999999))
        cache.set(f'register_code:{email}', code, timeout=300)

        if not send_email(email, code):
            User.objects.filter(email=email, is_active=False).delete()
            cache.delete(f'register_code:{email}')
            return Response({"detail": ["Не удалось отправить код на почту. Попробуйте позже."]}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'detail': ['Код подтверждения отправлен на почту.']}, status=status.HTTP_202_ACCEPTED)


@confirm_register_schema
class ConfirmRegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ConfirmRegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        code = cache.get(f'register_code:{email}')
        user = User.objects.filter(email=email, is_active=False).first()
        if not code or code != serializer.validated_data['code'] or not user:
            return Response({'detail': ['Неправильный или истёкший код.']}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.save(update_fields=["is_active"])
        cache.delete(f'register_code:{email}')

        return Response(UserSerializer(user, context={'request': request}).data, status=status.HTTP_200_OK)


@login_schema
class CookieTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        remember = request.data.get("remember_me", False)
        set_auth_cookies(response, response.data["access"], response.data["refresh"], remember)
        del response.data["access"], response.data["refresh"], response.data["remember_me"]
        return response


@logout_schema
class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie('access', path='/', samesite='None')
        response.delete_cookie('refresh', path='/', samesite='None')
        return response


@refresh_schema
class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        token = request.COOKIES.get("refresh")
        if not token:
            return Response({"detail": ["Некорректный refresh токен."]}, status=status.HTTP_401_UNAUTHORIZED)

        remember_me = bool(request.data.get("remember_me", False))

        request.data["refresh"] = token
        response = super().post(request, *args, **kwargs)

        set_auth_cookies(response, response.data["access"], response.data["refresh"], remember_me)

        del response.data["access"], response.data["refresh"]
        return response


@user_retrieve_schema
class UserRetrieveView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    queryset = User.objects.all()


@update_password_schema
class UpdatePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UpdatePasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_password = request.data.get("old_password")
        if not user.check_password(old_password):
            return Response({"detail": ["Неверный пароль."]}, status=400)

        user.set_password(request.data.get("password"))
        user.save()

        return Response({"detail": ["Пароль успешно изменён."]}, status=status.HTTP_200_OK)


@reset_password_schema
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    serializer_class = EmailSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        code = str(random.randint(100000, 999999))
        cache.set(f'reset_code:{email}', code, timeout=300)

        if not send_email(email, code):
            cache.delete(f'reset_code:{email}')
            return Response({"detail": ["Не удалось отправить код на почту. Попробуйте позже."]}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'detail': ['Код восстановления отправлен на почту.']}, status=status.HTTP_200_OK)


@confirm_reset_password_schema
class ConfirmResetPasswordView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        code = cache.get(f'reset_code:{email}')
        user = User.objects.filter(email=email).first()
        if not code or code != serializer.validated_data['code'] or not user:
            return Response({'detail': ['Неправильный или истёкший код.']}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=["password"])
        cache.delete(f'reset_code:{email}')

        return Response({'detail': ['Пароль успешно изменён.']}, status=status.HTTP_200_OK)


@update_email_schema
class UpdateEmailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NewEmailSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        code = str(random.randint(100000, 999999))
        cache.set(f'new_email:{email}', code, timeout=300)
        
        if not send_email(email, code):
            cache.delete(f'reset_code:{email}')
            return Response({"detail": ["Не удалось отправить код на почту. Попробуйте позже."]}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'detail': ['Код подтверждения отправлен на почту.']}, status=status.HTTP_200_OK)


@confirm_update_email_schema
class UpdateEmailConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmailWithCodeSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        code = cache.get(f'new_email:{email}')
        if not code or code != serializer.validated_data['code']:
            return Response({'detail': ['Неправильный или истёкший код.']}, status=status.HTTP_400_BAD_REQUEST)

        request.user.email = email
        request.user.save(update_fields=['email'])

        cache.delete(f'new_email:{email}')

        return Response(MeSerializer(request.user, context={'request': request}).data, status=status.HTTP_200_OK)


@user_profile_schema
class UserRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer
    
    def get_object(self):
        return User.objects.get(id=self.request.user.id)
    
    def get_serializer_class(self):
        if self.request.method == "GET":
            return MeSerializer
        return UpdateSerializer


@update_photo_schema
class UserPhotoUpdateView(generics.UpdateAPIView):
    http_method_names = ['patch']
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]
    serializer_class = UpdatePhotoSerializer

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


@vk_auth_schema
class VKAuthView(APIView):
    permission_classes = [AllowAny]
    serializer_class = VKAuthSerializer

    def post(self, request):
        if not settings.VK_CLIENT_ID or not settings.VK_REDIRECT_URI:
            return Response({'detail': ['Вход с помощью VK ID сейчас не возможен.']}, status=503)

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            access_token = vk.get_user(**serializer.validated_data)
            profile = vk.user_info(access_token)
            vk_id = int(profile['user_id'])
        except Exception:
            return Response({'detail': ['При авторизации через VK ID произошла ошибка.']}, status=502)

        user = User.objects.filter(vk_id=vk_id).first()

        if request.user.is_authenticated:
            if user and user.pk != request.user.pk:
                return Response({'detail': ['Этот VK ID уже привязан к другому пользователю.']}, status=409)
            if request.user.vk_id and request.user.vk_id != vk_id:
                return Response({'detail': ['К аккаунту уже привязан другой VK ID.']}, status=409)
            request.user.vk_id = vk_id

            request.user.save(update_fields=['vk_id'])

            return Response(MeSerializer(request.user, context={'request': request}).data)

        if not user:
            email = profile.get('email')
            pwd = gen_password(vk_id)
            # if email and not send_email(email, pwd):
            #     return Response({'detail': ['При авторизации через VK ID произошла ошибка.']}, status=502)
            email = email or f'vk-{vk_id}-{random.randint(100, 999)}@users.invalid'

            user = User.objects.create_user(
                email=email,
                password=pwd,
                vk_id=vk_id,
                first_name=str(profile.get('first_name') or '')[:64],
                last_name=str(profile.get('last_name') or '')[:64],
            )

        refresh = RefreshToken.for_user(user)
        response = Response(status=status.HTTP_200_OK)
        set_auth_cookies(response, str(refresh.access_token), str(refresh))
        return response
