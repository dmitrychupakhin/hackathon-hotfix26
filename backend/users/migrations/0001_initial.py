from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('email', models.EmailField(max_length=254, unique=True, verbose_name='email')),
                ('password', models.CharField(max_length=256, verbose_name='Пароль')),
                ('first_name', models.CharField(blank=True, default='', max_length=64, verbose_name='Имя')),
                ('last_name', models.CharField(blank=True, default='', max_length=64, verbose_name='Фамилия')),
                ('middle_name', models.CharField(blank=True, default='', max_length=64, verbose_name='Отчество')),
                ('photo', models.ImageField(blank=True, default='users/defaults/user.png', max_length=255, null=True, upload_to='users', verbose_name='Фото')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активность')),
                ('is_superuser', models.BooleanField(default=False, verbose_name='Администратор')),
                ('is_staff', models.BooleanField(default=False, verbose_name='Менеджер')),
            ],
            options={
                'verbose_name': 'пользователя',
                'verbose_name_plural': 'Пользователи',
            },
        ),
    ]
