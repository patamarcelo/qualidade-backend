# Generated by Django 4.1.7 on 2023-06-18 18:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0047_operacao_map_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='projeto',
            name='map_centro_id',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
