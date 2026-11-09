from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('chats', '0004_comparison_jobs')]

    operations = [
        migrations.AddField(model_name='chatmessage', name='answer_payload', field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name='chatmessage', name='citations', field=models.JSONField(default=list, blank=True)),
    ]
