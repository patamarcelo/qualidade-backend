# Generated by Django 5.0 on 2024-08-20 10:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0106_headerplanejamentoagricola'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='headerplanejamentoagricola',
            unique_together={('projeto', 'safra', 'ciclo')},
        ),
    ]
