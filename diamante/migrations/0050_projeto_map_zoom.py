# Generated by Django 4.1.7 on 2023-06-27 13:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0049_cultura_map_color_line'),
    ]

    operations = [
        migrations.AddField(
            model_name='projeto',
            name='map_zoom',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Zoom do Mapa', max_digits=4, null=True, verbose_name='Zoom do Mapa'),
        ),
    ]
