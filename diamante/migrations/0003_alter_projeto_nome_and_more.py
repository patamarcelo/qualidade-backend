# Generated by Django 4.1.7 on 2023-04-01 14:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0002_ciclo_alter_safra_safra'),
    ]

    operations = [
        migrations.AlterField(
            model_name='projeto',
            name='nome',
            field=models.CharField(help_text='Projeto', max_length=100, unique=True, verbose_name='Nome'),
        ),
        migrations.AlterField(
            model_name='projeto',
            name='quantidade_area_carr',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Area Carr'),
        ),
        migrations.AlterField(
            model_name='projeto',
            name='quantidade_area_produtiva',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Informar Area Produtiva', max_digits=10, null=True, verbose_name='Area Produtiva'),
        ),
        migrations.AlterField(
            model_name='projeto',
            name='quantidade_area_total',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Quantidade Area Total', max_digits=10, null=True, verbose_name='Area Total'),
        ),
        migrations.AlterField(
            model_name='talhao',
            name='id_unico',
            field=models.CharField(help_text='ID_Fazenda + Talhao', max_length=10, unique=True, verbose_name='ID_Unico'),
        ),
    ]
