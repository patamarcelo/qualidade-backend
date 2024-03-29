# Generated by Django 4.1.7 on 2023-10-04 14:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0065_colheita_peso_scs_limpo_e_seco'),
    ]

    operations = [
        migrations.AlterField(
            model_name='defensivo',
            name='tipo',
            field=models.CharField(choices=[('acaricida', 'Acaricida'), ('adjuvante', 'Adjuvante'), ('biologico', 'Biológico'), ('cobertura', 'Cobertura'), ('fertilizante', 'Fertilizante'), ('fungicida', 'Fungicida'), ('herbicida', 'Herbicida'), ('inseticida', 'Inseticida'), ('lubrificante', 'Lubrificante'), ('nutricao', 'Nutrição'), ('oleo_mineral_vegetal', 'Óleo Mineral/Vegetal'), ('protetor', 'Protetor'), ('regulador', 'Regulador'), ('semente', 'Semente')], max_length=40, verbose_name='Tipo'),
        ),
    ]
