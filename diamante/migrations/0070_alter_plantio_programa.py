# Generated by Django 4.1.7 on 2023-10-13 13:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0069_aplicacaoplantio'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plantio',
            name='programa',
            field=models.ForeignKey(blank=True, limit_choices_to={'ativo': True}, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='programa_related_plantio', to='diamante.programa'),
        ),
    ]