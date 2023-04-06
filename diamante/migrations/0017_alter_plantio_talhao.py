# Generated by Django 4.1.7 on 2023-04-06 11:49

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0016_alter_plantio_finalizado_colheita'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plantio',
            name='talhao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='plantios', to='diamante.talhao'),
        ),
    ]
