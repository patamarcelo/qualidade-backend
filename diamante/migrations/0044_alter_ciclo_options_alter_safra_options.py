# Generated by Django 4.1.7 on 2023-05-30 06:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0043_alter_plantio_cronograma_programa'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='ciclo',
            options={'verbose_name': 'Ciclo', 'verbose_name_plural': 'Ciclos'},
        ),
        migrations.AlterModelOptions(
            name='safra',
            options={'verbose_name': 'Safra', 'verbose_name_plural': 'Safras'},
        ),
    ]
