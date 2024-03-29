# Generated by Django 5.0 on 2024-01-09 13:42

import diamante.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diamante', '0084_alter_visitas_data'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='registrovisitas',
            options={'ordering': ['criados'], 'verbose_name': 'Visita - Registro', 'verbose_name_plural': 'Visitas - Registros'},
        ),
        migrations.AlterField(
            model_name='registrovisitas',
            name='image',
            field=models.ImageField(upload_to=diamante.models.get_img_upload_path, verbose_name='Imagem'),
        ),
        migrations.AlterUniqueTogether(
            name='visitas',
            unique_together={('fazenda', 'data')},
        ),
    ]
