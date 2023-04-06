# Generated by Django 4.1.7 on 2023-04-03 22:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0007_plantio_ciclo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plantio',
            name='ciclo',
            field=models.ForeignKey(default=0, on_delete=django.db.models.deletion.PROTECT, to='diamante.ciclo'),
            preserve_default=False,
        ),
    ]