# Generated by Django 4.1.7 on 2023-04-01 15:24

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0004_talhao_modulo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='talhao',
            name='fazenda',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.projeto'),
        ),
    ]
