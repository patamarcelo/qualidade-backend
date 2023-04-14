# Generated by Django 4.1.7 on 2023-04-13 15:02

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0019_alter_colheita_romaneio'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='operacao',
            options={'ordering': ['programa', 'operacao_numero'], 'verbose_name': 'Operação', 'verbose_name_plural': 'Operações'},
        ),
        migrations.AlterModelOptions(
            name='programa',
            options={'verbose_name': 'Programa', 'verbose_name_plural': 'Programas'},
        ),
        migrations.AddField(
            model_name='operacao',
            name='base_dap',
            field=models.BooleanField(default=False, help_text='Informar se a Operação é pelo prazo do Plantio', verbose_name='Prazo Base da Operação por DAP'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='base_emergencia',
            field=models.BooleanField(default=False, help_text='Informar se a Operação é pelo prazo de Emergencia', verbose_name='Prazo Base da Operação por Emergencia'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='estagio',
            field=models.CharField(blank=True, help_text='Nome do Estágio', max_length=120, null=True, verbose_name='Estagio'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='estagio_finalizado',
            field=models.BooleanField(default=False, help_text='Informar quando o estágio finalizar', verbose_name='Estagio Finalizado'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='estagio_iniciado',
            field=models.BooleanField(default=False, help_text='Informar quando o estágio iniciar', verbose_name='Estagio Iniciado'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='obs',
            field=models.TextField(blank=True, max_length=500, verbose_name='Observação'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='obs_1',
            field=models.TextField(blank=True, max_length=500, verbose_name='Observação 1'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='obs_2',
            field=models.TextField(blank=True, max_length=500, verbose_name='Observação 2'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='operacao_numero',
            field=models.IntegerField(blank=True, null=True, verbose_name='Número da Operação'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='prazo_dap',
            field=models.IntegerField(blank=True, null=True, verbose_name='DAP - Dias Após Plantio'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='prazo_emergencia',
            field=models.IntegerField(blank=True, null=True, verbose_name='Dias da Emergencia'),
        ),
        migrations.AddField(
            model_name='operacao',
            name='programa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='programa_related_operacao', to='diamante.programa'),
        ),
        migrations.AddField(
            model_name='plantio',
            name='data_emergencia',
            field=models.DateField(blank=True, help_text='Data Emergencia Talhao dd/mm/aaaa', null=True),
        ),
        migrations.AddField(
            model_name='plantio',
            name='programa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='programa_related_plantio', to='diamante.programa'),
        ),
        migrations.AddField(
            model_name='programa',
            name='ciclo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='diamante.ciclo'),
        ),
        migrations.AddField(
            model_name='programa',
            name='cultura',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='diamante.cultura'),
        ),
        migrations.AddField(
            model_name='programa',
            name='nome',
            field=models.CharField(blank=True, help_text='Nome do Programa', max_length=120, null=True, verbose_name='Nome Programa'),
        ),
        migrations.AddField(
            model_name='programa',
            name='programa_por_data',
            field=models.BooleanField(default=True, help_text='Define se o programa é calculado por data', verbose_name='Regra por data'),
        ),
        migrations.AddField(
            model_name='programa',
            name='programa_por_estagio',
            field=models.BooleanField(default=False, help_text='Define se o programa é calculado por Estágio', verbose_name='Regra por estágio'),
        ),
        migrations.AddField(
            model_name='programa',
            name='safra',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='diamante.safra'),
        ),
    ]