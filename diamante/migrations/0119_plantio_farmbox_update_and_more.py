# Generated by Django 5.0 on 2024-11-12 15:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0118_alter_plantioextratoarea_finalizado_plantio'),
    ]

    operations = [
        migrations.AddField(
            model_name='plantio',
            name='farmbox_update',
            field=models.BooleanField(default=True, help_text='Falso caso não seja pra atualizar com os dados do Farmbox', verbose_name='Atualziar via Farmbox'),
        ),
        migrations.AlterField(
            model_name='plantioextratoarea',
            name='data_plantio',
            field=models.DateField(help_text='dd/mm/aaaa - Data Efetiva de Plantio', null=True),
        ),
    ]