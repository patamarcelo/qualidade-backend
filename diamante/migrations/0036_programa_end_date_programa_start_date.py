# Generated by Django 4.1.7 on 2023-04-25 15:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0035_cultura_id_farmbox'),
    ]

    operations = [
        migrations.AddField(
            model_name='programa',
            name='end_date',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Prevista Término Programa / Plantio', null=True),
        ),
        migrations.AddField(
            model_name='programa',
            name='start_date',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Prevista Inínicio Programa / Plantio', null=True),
        ),
    ]
