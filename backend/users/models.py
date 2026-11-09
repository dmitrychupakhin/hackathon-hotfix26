from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

from utils.mixins import TimeStampedMixin
from .instructions import DEFAULT_AI_INSTRUCTIONS


class UserManager(BaseUserManager):
    def get_by_natural_key(self, email):
        return self.get(**{self.model.USERNAME_FIELD: email})

    def create_user(self, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, TimeStampedMixin):
    email = models.EmailField(unique=True, verbose_name='email')
    password = models.CharField(max_length=256, verbose_name='Пароль')

    vk_id = models.PositiveBigIntegerField(unique=True, blank=True, null=True, verbose_name='VK ID')

    first_name = models.CharField(max_length=64, blank=True, default='', verbose_name='Имя')
    last_name = models.CharField(max_length=64, blank=True, default='', verbose_name='Фамилия')
    middle_name = models.CharField(max_length=64, blank=True, default='', verbose_name='Отчество')
    system_prompt = models.TextField(max_length=8000, blank=True, default=DEFAULT_AI_INSTRUCTIONS, verbose_name='Инструкции для ИИ')

    photo = models.ImageField(max_length=255, upload_to="users", blank=True, null=True, verbose_name='Фото', default='users/defaults/user.png')

    is_active = models.BooleanField(default=True, verbose_name='Активность')
    is_superuser = models.BooleanField(default=False, verbose_name='Администратор')
    is_staff = models.BooleanField(default=False, verbose_name='Менеджер')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    class Meta:
        verbose_name = 'пользователя'
        verbose_name_plural = 'Пользователи'
