# Generated by Django 4.1.7 on 2023-04-03 22:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0009_alter_talhao_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='talhao',
            options={'ordering': ['fazenda__nome', 'id_talhao'], 'verbose_name': 'Talhao', 'verbose_name_plural': 'Talhoes'},
        ),
    ]
