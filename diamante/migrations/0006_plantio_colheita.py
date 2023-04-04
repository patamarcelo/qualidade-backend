# Generated by Django 4.1.7 on 2023-04-03 21:57

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0005_alter_talhao_fazenda'),
    ]

    operations = [
        migrations.CreateModel(
            name='Plantio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('finalizado_plantio', models.BooleanField(default=True, help_text='Finalizado o Plantio', verbose_name='Finalizado')),
                ('finalizado_colheita', models.BooleanField(default=False, help_text='Finalizado o Plantio', verbose_name='Finalizado')),
                ('area_colheita', models.DecimalField(decimal_places=2, help_text='Area Plantada / ha', max_digits=8, verbose_name='Area Colheita')),
                ('area_parcial', models.DecimalField(blank=True, decimal_places=2, help_text='Area Parcial / ha', max_digits=8, null=True, verbose_name='Area Parcial Colhida')),
                ('data_plantio', models.DateField(blank=True, default=django.utils.timezone.now, help_text='dd/mm/aaaa', null=True)),
                ('safra', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.safra')),
                ('talhao', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.talhao')),
                ('variedade', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.variedade')),
            ],
            options={
                'verbose_name': 'Plantio',
                'verbose_name_plural': 'Plantios',
                'ordering': ['data_plantio'],
            },
        ),
        migrations.CreateModel(
            name='Colheita',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('data_colheita', models.DateField(blank=True, help_text='dd/mm/aaaa', null=True)),
                ('placa', models.CharField(help_text='Placa do Veículo', max_length=40, verbose_name='Placa')),
                ('motorista', models.CharField(help_text='Nome do Motorista', max_length=40, verbose_name='Nome Motorista')),
                ('romaneio', models.CharField(help_text='Número do Romaneio', max_length=40, unique=True, verbose_name='Romaneio')),
                ('peso_umido', models.DecimalField(decimal_places=2, help_text='Peso Líquido Antes dos descontos', max_digits=14, verbose_name='Peso Úmido')),
                ('peso_liquido', models.DecimalField(decimal_places=2, help_text='Peso Líquido Depois dos descontos', max_digits=14, verbose_name='Peso Líquido')),
                ('deposito', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.deposito')),
                ('plantio', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.plantio')),
            ],
            options={
                'verbose_name': 'Colheita',
                'verbose_name_plural': 'Colheitas',
                'ordering': ['data_colheita'],
                'unique_together': {('plantio', 'romaneio')},
            },
        ),
    ]
