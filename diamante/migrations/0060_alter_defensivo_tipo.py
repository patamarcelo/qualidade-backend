# Generated by Django 4.1.7 on 2023-08-14 08:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0059_plantiodetail_alter_colheita_plantio'),
    ]

    operations = [
        migrations.AlterField(
            model_name='defensivo',
            name='tipo',
            field=models.CharField(choices=[('acaricida', 'Acaricida'), ('adjuvante', 'Adjuvante'), ('biologico', 'Biológico'), ('fertilizante', 'Fertilizante'), ('fungicida', 'Fungicida'), ('herbicida', 'Herbicida'), ('inseticida', 'Inseticida'), ('lubrificante', 'Lubrificante'), ('nutricao', 'Nutrição'), ('oleo_mineral_vegetal', 'Óleo Mineral/Vegetal'), ('protetor', 'Protetor'), ('regulador', 'Regulador')], max_length=40, verbose_name='Tipo'),
        ),
    ]
