# Generated by Django 5.0 on 2024-05-21 15:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0091_alter_colheita_unique_together_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='fazenda',
            name='id_encarregado_farmbox',
            field=models.IntegerField(blank=True, null=True, unique=True, verbose_name='ID Encarregado FarmBox'),
        ),
        migrations.AddField(
            model_name='fazenda',
            name='id_responsavel_farmbox',
            field=models.IntegerField(blank=True, null=True, unique=True, verbose_name='ID Responsavel FarmBox'),
        ),
        migrations.AddField(
            model_name='safra',
            name='id_farmbox',
            field=models.IntegerField(blank=True, null=True, unique=True, verbose_name='ID FarmBox'),
        ),
    ]
