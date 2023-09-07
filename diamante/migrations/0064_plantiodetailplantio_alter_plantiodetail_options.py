# Generated by Django 4.1.7 on 2023-09-07 14:23

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0063_alter_colheita_unique_together'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlantioDetailPlantio',
            fields=[
            ],
            options={
                'verbose_name': 'Plantio - Resumo Plantio',
                'verbose_name_plural': 'Plantios - Resumo Plantio',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('diamante.plantio',),
        ),
        migrations.AlterModelOptions(
            name='plantiodetail',
            options={'verbose_name': 'Plantio - Resumo Colheita', 'verbose_name_plural': 'Plantios - Resumo Colheita'},
        ),
    ]
