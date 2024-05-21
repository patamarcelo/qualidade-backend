# Generated by Django 5.0 on 2024-05-21 16:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0094_defensivo_id_farmbox'),
    ]

    operations = [
        migrations.AlterField(
            model_name='defensivo',
            name='formulacao',
            field=models.CharField(choices=[('liquido', 'Líquido'), ('solido', 'Sólido'), ('unidade', 'Unidade')], max_length=40, verbose_name='Formulação'),
        ),
    ]
