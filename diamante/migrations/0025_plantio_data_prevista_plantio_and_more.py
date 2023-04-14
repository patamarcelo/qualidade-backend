# Generated by Django 4.1.7 on 2023-04-14 15:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0024_alter_defensivo_unidade_medida'),
    ]

    operations = [
        migrations.AddField(
            model_name='plantio',
            name='data_prevista_plantio',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Projetada para o Plantio', null=True),
        ),
        migrations.AddField(
            model_name='plantio',
            name='data_programa_1',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Etapa 1', null=True),
        ),
        migrations.AddField(
            model_name='plantio',
            name='data_programa_2',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Etapa 2', null=True),
        ),
        migrations.AlterField(
            model_name='plantio',
            name='data_emergencia',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Emergencia Talhao ', null=True),
        ),
        migrations.AlterField(
            model_name='plantio',
            name='data_plantio',
            field=models.DateField(blank=True, help_text='dd/mm/aaaa - Data Efetiva de Plantio', null=True),
        ),
    ]
