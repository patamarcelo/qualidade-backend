# Generated by Django 4.1.7 on 2023-04-13 07:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0018_plantio_area_aproveito'),
    ]

    operations = [
        migrations.AlterField(
            model_name='colheita',
            name='romaneio',
            field=models.CharField(help_text='Número do Romaneio', max_length=40, verbose_name='Romaneio'),
        ),
    ]