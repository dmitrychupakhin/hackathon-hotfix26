from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class DetailListSerializer(serializers.Serializer):
    detail = serializers.ListField(child=serializers.CharField())


class EmptySerializer(serializers.Serializer):
    pass


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()
    remember_me = serializers.BooleanField(required=False, default=False)


class VKAuthSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=2048, trim_whitespace=False)
    code_verifier = serializers.CharField(min_length=43, max_length=128, trim_whitespace=False)
    device_id = serializers.CharField(max_length=256)
    state = serializers.CharField(max_length=256, trim_whitespace=False)


class RegisterSerializer(serializers.ModelSerializer):
    confirm = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(validators=[validate_password])

    class Meta:
        model = User
        fields = ('email', 'password', 'confirm')
        write_only_fields = ('confirm',)

    def validate_email(self, value):
        if User.objects.filter(email=value, is_active=True).exists():
            raise serializers.ValidationError('Пользователь с таким email уже существует.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm']:
            raise serializers.ValidationError({'detail': 'Пароли не совпадают.'})
        attrs.pop('confirm', None)
        return attrs


class ConfirmRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(required=True)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    remember_me = serializers.BooleanField(default=False)

    def validate(self, attrs):
        data = super().validate(attrs)
        data["remember_me"] = attrs.get("remember_me", False)
        return data


class TokenRefreshSerializer(serializers.Serializer):
    remember_me = serializers.BooleanField(default=False)


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'middle_name', 'photo')


class MeSerializer(UserSerializer):

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('email', 'system_prompt')


class UpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'middle_name', 'system_prompt')
        extra_kwargs = {
            'first_name': {'required': True, 'allow_blank': False},
            'last_name': {'required': True, 'allow_blank': False},
        }


class UpdatePhotoSerializer(serializers.ModelSerializer):
    photo = serializers.ImageField(required=True)

    class Meta:
        model = User
        fields = ('photo',)


class UpdatePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    password = serializers.CharField(required=True, validators=[validate_password])
    confirm = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm']:
            raise serializers.ValidationError({'detail': 'Пароли не совпадают.'})
        attrs.pop('confirm', None)
        return attrs


class BaseEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    should_exist = None

    def validate_email(self, value):
        exists = User.objects.filter(email=value).exists()
        if self.should_exist is True and not exists:
            raise serializers.ValidationError('Пользователя с таким email не существует.')
        if self.should_exist is False and exists:
            raise serializers.ValidationError('Этот email уже занят.')
        return value


class EmailSerializer(BaseEmailSerializer):
    should_exist = True


class NewEmailSerializer(BaseEmailSerializer):
    should_exist = False


class EmailWithCodeSerializer(NewEmailSerializer):
    code = serializers.CharField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(required=True)
    password = serializers.CharField(required=True, validators=[validate_password])
    confirm = serializers.CharField(required=True, write_only=True)

    def validate_email(self, value):
        exists = User.objects.filter(email=value).exists()
        if not exists:
            raise serializers.ValidationError('Пользователя с таким email не существует.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm']:
            raise serializers.ValidationError({'detail': 'Пароли не совпадают.'})
        attrs.pop('confirm', None)
        return attrs


class FieldErrorsSerializer(serializers.Serializer):
    non_field_errors = serializers.ListField(child=serializers.CharField(), required=False)


class RegisterFieldErrorsSerializer(FieldErrorsSerializer):
    email = serializers.ListField(child=serializers.CharField(), required=False)
    password = serializers.ListField(child=serializers.CharField(), required=False)
    confirm = serializers.ListField(child=serializers.CharField(), required=False)


class ConfirmRegisterFieldErrorsSerializer(FieldErrorsSerializer):
    email = serializers.ListField(child=serializers.CharField(), required=False)
    code = serializers.ListField(child=serializers.CharField(), required=False)


class LoginFieldErrorsSerializer(FieldErrorsSerializer):
    email = serializers.ListField(child=serializers.CharField(), required=False)
    password = serializers.ListField(child=serializers.CharField(), required=False)
    remember_me = serializers.ListField(child=serializers.CharField(), required=False)


class VKAuthFieldErrorsSerializer(FieldErrorsSerializer):
    code = serializers.ListField(child=serializers.CharField(), required=False)
    code_verifier = serializers.ListField(child=serializers.CharField(), required=False)
    device_id = serializers.ListField(child=serializers.CharField(), required=False)
    state = serializers.ListField(child=serializers.CharField(), required=False)


class UpdatePasswordFieldErrorsSerializer(FieldErrorsSerializer):
    old_password = serializers.ListField(child=serializers.CharField(), required=False)
    password = serializers.ListField(child=serializers.CharField(), required=False)
    confirm = serializers.ListField(child=serializers.CharField(), required=False)


class EmailFieldErrorsSerializer(FieldErrorsSerializer):
    email = serializers.ListField(child=serializers.CharField(), required=False)


class EmailWithCodeFieldErrorsSerializer(EmailFieldErrorsSerializer):
    code = serializers.ListField(child=serializers.CharField(), required=False)


class ResetPasswordFieldErrorsSerializer(FieldErrorsSerializer):
    email = serializers.ListField(child=serializers.CharField(), required=False)
    code = serializers.ListField(child=serializers.CharField(), required=False)
    password = serializers.ListField(child=serializers.CharField(), required=False)
    confirm = serializers.ListField(child=serializers.CharField(), required=False)


class UpdateFieldErrorsSerializer(FieldErrorsSerializer):
    first_name = serializers.ListField(child=serializers.CharField(), required=False)
    last_name = serializers.ListField(child=serializers.CharField(), required=False)
    middle_name = serializers.ListField(child=serializers.CharField(), required=False)
    system_prompt = serializers.ListField(child=serializers.CharField(), required=False)


class UpdatePhotoFieldErrorsSerializer(FieldErrorsSerializer):
    photo = serializers.ListField(child=serializers.CharField(), required=False)
