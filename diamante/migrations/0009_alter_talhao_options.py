# Generated by Django 4.1.7 on 2023-04-03 22:22

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0008_alter_plantio_ciclo'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='talhao',
            options={'ordering': ['fazenda__nome', 'id_unico'], 'verbose_name': 'Talhao', 'verbose_name_plural': 'Talhoes'},
        ),
    ]
