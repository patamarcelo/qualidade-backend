# Generated by Django 4.1.7 on 2023-04-03 22:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0006_plantio_colheita'),
    ]

    operations = [
        migrations.AddField(
            model_name='plantio',
            name='ciclo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='diamante.ciclo'),
        ),
    ]