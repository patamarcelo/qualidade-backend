# Generated by Django 4.1.7 on 2023-11-06 15:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0071_alter_operacao_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='programa',
            name='versao',
            field=models.IntegerField(blank=True, null=True, verbose_name='Versão Atual'),
        ),
    ]
