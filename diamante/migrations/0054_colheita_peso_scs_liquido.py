# Generated by Django 4.1.7 on 2023-08-01 15:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0053_deposito_nome_fantasia'),
    ]

    operations = [
        migrations.AddField(
            model_name='colheita',
            name='peso_scs_liquido',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Peso Líquido Calculado em Sacos de 60Kg', max_digits=8, null=True, verbose_name='Sacos Liquido'),
        ),
    ]
