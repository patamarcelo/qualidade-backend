# Generated by Django 5.0 on 2024-08-19 14:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0103_colheitaplantioextratoarea_plantioextratoarea'),
    ]

    operations = [
        migrations.AddField(
            model_name='cultura',
            name='id_cultura_dif_protheus_planejamento',
            field=models.CharField(blank=True, help_text=' ID Cultura Planejamento Agrícola Protheus / mesma cultura diferentes codigos ( feijao)', max_length=20, null=True, verbose_name='ID Cultura'),
        ),
    ]
