# Generated by Django 5.0 on 2024-11-30 10:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0120_alter_aplicacao_dose'),
    ]

    operations = [
        migrations.AddField(
            model_name='programa',
            name='variedade',
            field=models.ManyToManyField(blank=True, default=None, to='diamante.variedade'),
        ),
    ]