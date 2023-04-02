# Generated by Django 4.1.7 on 2023-04-01 13:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Cultura',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('cultura', models.CharField(help_text='Cultura', max_length=100, unique=True, verbose_name='Cultura')),
                ('id_d', models.PositiveIntegerField(unique=True, verbose_name='ID_D')),
                ('tipo_producao', models.CharField(blank=True, max_length=20, null=True, verbose_name='Tipo Produção')),
            ],
            options={
                'verbose_name': 'Cultura',
                'verbose_name_plural': 'Culturas',
                'ordering': ['cultura'],
            },
        ),
        migrations.CreateModel(
            name='Deposito',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('nome', models.CharField(help_text='Depósito', max_length=100, unique=True, verbose_name='Nome')),
                ('id_d', models.PositiveIntegerField(unique=True, verbose_name='ID_D')),
            ],
            options={
                'verbose_name': 'Depósito',
                'verbose_name_plural': 'Depósitos',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='Fazenda',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('nome', models.CharField(help_text='Fazenda', max_length=100, unique=True, verbose_name='Nome')),
                ('id_d', models.PositiveIntegerField(unique=True, verbose_name='ID_D')),
            ],
            options={
                'verbose_name': 'Fazenda',
                'verbose_name_plural': 'Fazenda',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='Safra',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('safra', models.CharField(help_text='Safra e Ciclo', max_length=100, unique=True, verbose_name='Safra')),
            ],
            options={
                'verbose_name': 'Safra',
                'verbose_name_plural': 'Safras',
                'ordering': ['safra'],
            },
        ),
        migrations.CreateModel(
            name='Variedade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('variedade', models.CharField(max_length=100, unique=True, verbose_name='Variedade')),
                ('nome_fantasia', models.CharField(blank=True, max_length=100, null=True, verbose_name='Nome Fant.')),
                ('dias_ciclo', models.PositiveIntegerField(default=0, verbose_name='Quantidade Dias do Ciclo')),
                ('dias_germinacao', models.PositiveIntegerField(default=5, verbose_name='Quantidade Dias da Germinação')),
                ('cultura', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.cultura')),
            ],
            options={
                'verbose_name': 'Variedade',
                'verbose_name_plural': 'Variedades',
                'ordering': ['variedade'],
            },
        ),
        migrations.CreateModel(
            name='Talhao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('id_talhao', models.CharField(help_text='Talhao', max_length=100, verbose_name='ID Talhao')),
                ('id_unico', models.IntegerField(help_text='ID_Fazenda + Talhao', unique=True, verbose_name='ID_Unico')),
                ('area_total', models.DecimalField(decimal_places=2, max_digits=6, verbose_name='Area Total')),
                ('fazenda', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.fazenda')),
            ],
            options={
                'verbose_name': 'Talhao',
                'verbose_name_plural': 'Talhoes',
                'ordering': ['id_talhao'],
            },
        ),
        migrations.CreateModel(
            name='Projeto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('nome', models.CharField(help_text='Fazenda', max_length=100, unique=True, verbose_name='Nome')),
                ('id_d', models.IntegerField(unique=True, verbose_name='ID_D')),
                ('quantidade_area_produtiva', models.PositiveIntegerField(blank=True, help_text='Informar Area Produtiva', null=True, verbose_name='Area Produtiva')),
                ('quantidade_area_carr', models.PositiveIntegerField(blank=True, null=True, verbose_name='Area Carr')),
                ('quantidade_area_total', models.PositiveIntegerField(blank=True, help_text='Quantidade Area Total', null=True, verbose_name='Area Total')),
                ('fazenda', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.fazenda')),
            ],
            options={
                'verbose_name': 'Projeto',
                'verbose_name_plural': 'Projeto',
                'ordering': ['nome'],
            },
        ),
    ]