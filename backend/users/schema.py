from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema, extend_schema_view

from .serializers import (
    ConfirmRegisterFieldErrorsSerializer,
    ConfirmRegisterSerializer,
    DetailListSerializer,
    EmailFieldErrorsSerializer,
    EmailSerializer,
    EmailWithCodeFieldErrorsSerializer,
    EmailWithCodeSerializer,
    EmptySerializer,
    LoginFieldErrorsSerializer,
    LoginSerializer,
    MeSerializer,
    NewEmailSerializer,
    RegisterFieldErrorsSerializer,
    RegisterSerializer,
    ResetPasswordFieldErrorsSerializer,
    ResetPasswordSerializer,
    TokenRefreshSerializer,
    UpdateFieldErrorsSerializer,
    UpdatePasswordFieldErrorsSerializer,
    UpdatePasswordSerializer,
    UpdatePhotoFieldErrorsSerializer,
    UpdatePhotoSerializer,
    UpdateSerializer,
    UserSerializer,
    VKAuthFieldErrorsSerializer,
    VKAuthSerializer,
)


register_schema = extend_schema_view(post=extend_schema(
    summary="Регистрация пользователя",
    tags=["Регистрация"],
    request=RegisterSerializer,
    responses={
        202: DetailListSerializer,
        400: PolymorphicProxySerializer(
            component_name="RegisterError",
            serializers=[DetailListSerializer, RegisterFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        503: DetailListSerializer,
    },
))

confirm_register_schema = extend_schema_view(post=extend_schema(
    summary="Подтверждение регистрации",
    tags=["Регистрация"],
    request=ConfirmRegisterSerializer,
    responses={
        200: UserSerializer,
        400: PolymorphicProxySerializer(
            component_name="ConfirmRegisterError",
            serializers=[DetailListSerializer, ConfirmRegisterFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
    },
))

login_schema = extend_schema_view(post=extend_schema(
    summary="Авторизация (cookie)",
    tags=["Авторизация"],
    description=" ",
    request=LoginSerializer,
    responses={
        200: EmptySerializer,
        400: PolymorphicProxySerializer(
            component_name="LoginError",
            serializers=[DetailListSerializer, LoginFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        401: DetailListSerializer,
    },
))

logout_schema = extend_schema_view(post=extend_schema(
    summary="Выход из аккаунта",
    tags=["Авторизация"],
    request=None,
    responses={204: None},
))

vk_auth_schema = extend_schema_view(post=extend_schema(
    summary="Вход, регистрация или привязка VK ID",
    tags=["Авторизация"],
    request=VKAuthSerializer,
    responses={
        200: EmptySerializer,
        400: PolymorphicProxySerializer(
            component_name="VKAuthError",
            serializers=[DetailListSerializer, VKAuthFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        401: DetailListSerializer,
        409: DetailListSerializer,
        502: DetailListSerializer,
        503: DetailListSerializer,
    },
))

refresh_schema = extend_schema_view(post=extend_schema(
    summary="Обновление refresh и access",
    tags=["Авторизация"],
    request=TokenRefreshSerializer,
    responses={200: EmptySerializer, 401: DetailListSerializer},
))

user_retrieve_schema = extend_schema_view(get=extend_schema(
    summary="Пользователь по id",
    tags=["Пользователи"],
    responses={200: UserSerializer, 401: DetailListSerializer, 404: DetailListSerializer},
))

update_password_schema = extend_schema_view(post=extend_schema(
    summary="Изменение пароля по старому",
    tags=["Личный кабинет"],
    request=UpdatePasswordSerializer,
    responses={
        200: DetailListSerializer,
        400: PolymorphicProxySerializer(
            component_name="UpdatePasswordError",
            serializers=[DetailListSerializer, UpdatePasswordFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
    },
))

reset_password_schema = extend_schema_view(post=extend_schema(
    summary="Запрос на восстановление пароля по почте",
    tags=["Личный кабинет"],
    request=EmailSerializer,
    responses={
        200: DetailListSerializer,
        400: PolymorphicProxySerializer(
            component_name="ResetPasswordRequestError",
            serializers=[DetailListSerializer, EmailFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        503: DetailListSerializer,
    },
))

confirm_reset_password_schema = extend_schema_view(post=extend_schema(
    summary="Восстановление пароля по почте",
    tags=["Личный кабинет"],
    request=ResetPasswordSerializer,
    responses={
        200: DetailListSerializer,
        400: PolymorphicProxySerializer(
            component_name="ConfirmResetPasswordError",
            serializers=[DetailListSerializer, ResetPasswordFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
    },
))

update_email_schema = extend_schema_view(post=extend_schema(
    summary="Запрос на смену почты",
    tags=["Личный кабинет"],
    request=NewEmailSerializer,
    responses={
        200: DetailListSerializer,
        400: PolymorphicProxySerializer(
            component_name="UpdateEmailError",
            serializers=[DetailListSerializer, EmailFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        401: DetailListSerializer,
        503: DetailListSerializer,
    },
))

confirm_update_email_schema = extend_schema_view(post=extend_schema(
    summary="Подтверждение смены почты",
    tags=["Личный кабинет"],
    request=EmailWithCodeSerializer,
    responses={
        200: MeSerializer,
        400: PolymorphicProxySerializer(
            component_name="ConfirmUpdateEmailError",
            serializers=[DetailListSerializer, EmailWithCodeFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        401: DetailListSerializer,
    },
))

user_profile_schema = extend_schema_view(
    get=extend_schema(
        summary="Получение данных пользователя",
        tags=["Личный кабинет"],
        responses={200: MeSerializer, 401: DetailListSerializer},
    ),
    put=extend_schema(
        summary="Редактировать профиль пользователя",
        tags=["Личный кабинет"],
        request=UpdateSerializer,
        responses={
            200: UpdateSerializer,
            400: PolymorphicProxySerializer(
                component_name="UpdateProfileError",
                serializers=[DetailListSerializer, UpdateFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
        },
    ),
    patch=extend_schema(
        summary="Редактировать поле в профиле пользователя",
        tags=["Личный кабинет"],
        request=UpdateSerializer,
        responses={
            200: UpdateSerializer,
            400: PolymorphicProxySerializer(
                component_name="PatchProfileError",
                serializers=[DetailListSerializer, UpdateFieldErrorsSerializer],
                resource_type_field_name=None,
            ),
            401: DetailListSerializer,
        },
    ),
)


update_photo_schema = extend_schema_view(patch=extend_schema(
    summary="Изменение фото профиля",
    tags=["Личный кабинет"],
    request=UpdatePhotoSerializer,
    responses={
        200: UpdatePhotoSerializer,
        400: PolymorphicProxySerializer(
            component_name="UpdatePhotoError",
            serializers=[DetailListSerializer, UpdatePhotoFieldErrorsSerializer],
            resource_type_field_name=None,
        ),
        401: DetailListSerializer,
    },
))
