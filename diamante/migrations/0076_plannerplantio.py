# Generated by Django 4.1.7 on 2023-11-20 07:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0075_cicloatual'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlannerPlantio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criados', models.DateTimeField(auto_now_add=True, verbose_name='Criação')),
                ('modificado', models.DateTimeField(auto_now=True, verbose_name='Atualização')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('start_date', models.DateField(blank=True, help_text='dd/mm/aaaa - Data Prevista Inínicio Programa / Plantio', null=True)),
                ('area', models.DecimalField(blank=True, decimal_places=2, help_text='Informar Area Prevista', max_digits=10, null=True, verbose_name='Area Prevista')),
                ('ciclo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.ciclo')),
                ('cultura', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.cultura')),
                ('projeto', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.projeto')),
                ('safra', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='diamante.safra')),
            ],
            options={
                'verbose_name': 'Planejamento Plantio',
                'verbose_name_plural': 'Planejamento Plantios',
                'ordering': ['start_date'],
                'unique_together': {('projeto', 'cultura', 'ciclo', 'safra', 'start_date')},
            },
        ),
    ]