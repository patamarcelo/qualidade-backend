# Generated by Django 5.0 on 2024-05-21 16:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aviacao', '0011_remove_ordemdeservico_tempo_aplicacao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ordemdeservico',
            name='tipo_servico',
            field=models.CharField(choices=[('acaricida', 'Acaricida'), ('adjuvante', 'Adjuvante'), ('biologico', 'Biológico'), ('cobertura', 'Cobertura'), ('fertilizante', 'Fertilizante'), ('fungicida', 'Fungicida'), ('herbicida', 'Herbicida'), ('inseticida', 'Inseticida'), ('lubrificante', 'Lubrificante'), ('nutricao', 'Nutrição'), ('oleo_mineral_vegetal', 'Óleo Mineral/Vegetal'), ('operacao', 'Operação'), ('protetor', 'Protetor'), ('regulador', 'Regulador'), ('semente', 'Semente')], max_length=80, verbose_name='Tipo Serviço'),
        ),
    ]
