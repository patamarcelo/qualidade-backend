from django.contrib import admin

# Register your models here.
from .models import *

from django_json_widget.widgets import JSONEditorWidget


@admin.register(TecnicoAgricola)
class TecnicoAgricolaAdmin(admin.ModelAdmin):
    list_display = ("nome", "crea_number")

@admin.register(Aeronave)
class AeronaveAdmin(admin.ModelAdmin):
    list_display = ("prefixo",)

@admin.register(Pista)
class PistaAdmin(admin.ModelAdmin):
    list_display = ("projeto","nome", "coordenadas")
    
    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="50vh", mode="tree")
        },
    }

@admin.register(Piloto)
class PilotoAdmin(admin.ModelAdmin):
    list_display = ("nome", "anac")

@admin.register(OrdemDeServico)
class OrdemDeServicoAdmin(admin.ModelAdmin):
    list_display = ("numero", "data")

@admin.register(CondicoesMeteorologicas)
class CondicoesMeteorologicasAdmin(admin.ModelAdmin):
    list_display = ("os", "temperatura_inicial", "temperatura_final")

@admin.register(TempoAplicacao)
class TempoAplicacaoAdmin(admin.ModelAdmin):
    list_display = ("os", "inicio_aplicacao", "final_aplicacao")

@admin.register(AplicacaoAviao)
class AplicacaoAviaoAdmin(admin.ModelAdmin):
    list_display = ("os", "defensivo", "dose", 'ativo')

@admin.register(TabelaPilotos)
class TabelaPilotosAdmin(admin.ModelAdmin):
    list_display = ("safra", "ciclo", "vazao", "preco", 'ativo')
