# Generated by Django 4.1.7 on 2023-10-16 10:19

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0070_alter_plantio_programa'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='operacao',
            unique_together={('estagio', 'programa')},
        ),
    ]
