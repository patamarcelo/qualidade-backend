# Generated by Django 4.1.7 on 2023-04-04 17:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0015_aplicacoes_operacao_programa_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plantio',
            name='finalizado_colheita',
            field=models.BooleanField(default=False, help_text='Finalizada a Colheita', verbose_name='Finalizado'),
        ),
    ]