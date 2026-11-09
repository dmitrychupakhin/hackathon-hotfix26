from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0002_user_vk_id')]

    operations = [
        migrations.AddField(
            model_name='user',
            name='system_prompt',
            field=models.TextField(blank=True, default='', max_length=8000, verbose_name='Системный промпт'),
        ),
    ]
