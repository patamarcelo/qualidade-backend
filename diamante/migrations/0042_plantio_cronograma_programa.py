# Generated by Django 4.1.7 on 2023-05-26 17:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0041_alter_plantio_variedade'),
    ]

    operations = [
        migrations.AddField(
            model_name='plantio',
            name='cronograma_programa',
            field=models.JSONField(null=True),
        ),
    ]
