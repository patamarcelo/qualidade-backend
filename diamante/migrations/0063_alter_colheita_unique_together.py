# Generated by Django 4.1.7 on 2023-08-22 15:51

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0062_colheita_bandinha_colheita_desconto_bandinha'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='colheita',
            unique_together={('plantio', 'romaneio', 'ticket'), ('romaneio', 'plantio')},
        ),
    ]
