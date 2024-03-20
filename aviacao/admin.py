from django.contrib import admin

# Register your models here.
from .models import *

from django_json_widget.widgets import JSONEditorWidget


class AplicacaoAviaoInline(admin.StackedInline):
    model = AplicacaoAviao
    extra = 0
    fields = ["defensivo", "dose", "ativo"]
    autocomplete_fields = ["defensivo"]


class CondicoesMeteorologicasInline(admin.StackedInline):
    model = CondicoesMeteorologicas
    extra = 0
    fields = [
        "temperatura_inicial",
        "temperatura_final",
        "umidade_relativa_incial",
        "umidade_relativa_final",
    ]


@admin.register(TecnicoAgricola)
class TecnicoAgricolaAdmin(admin.ModelAdmin):
    list_display = ("nome", "crea_number")


@admin.register(Aeronave)
class AeronaveAdmin(admin.ModelAdmin):
    list_display = ("prefixo",)


@admin.register(Pista)
class PistaAdmin(admin.ModelAdmin):
    list_display = ("projeto", "nome", "coordenadas")

    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="50vh", mode="tree")
        },
    }


@admin.register(Piloto)
class PilotoAdmin(admin.ModelAdmin):
    list_display = ("nome", "anac")


@admin.register(Gerente)
class GerenteAdmin(admin.ModelAdmin):
    # criar get projetos list display
    list_display = ["nome"]
    search_fields = ["nome"]


@admin.register(OrdemDeServico)
class OrdemDeServicoAdmin(admin.ModelAdmin):
    list_display = ("numero", "data")
    filter_horizontal = ("ajudante",)
    readonly_fields = ["criados"]
    autocomplete_fields = ["encarregado_autoriza"]
    inlines = [AplicacaoAviaoInline, CondicoesMeteorologicasInline]
    fieldsets = [
        (
            "Dados",
            {
                "fields": (
                    ("ativo", "criados"),
                    ("numero", "data"),
                    ("os_file"),
                    (
                        "data_inicial",
                        "data_final",
                    ),
                    ("cultura", "tipo_servico"),
                    ("area", "volume"),
                    ("horimetro_inicial", "horimetro_final"),
                    ("combustivel", "oleo_lubrificante"),
                    ("ajudante"),
                    ("encarregado_autoriza"),
                ),
            },
        ),
        (
            "Aeronave",
            {"fields": (("aeronave"), ("piloto"), ("uso_gps",))},
        ),
        (
            "Responsável",
            {"fields": (("tecnico_agricola_executor"),)},
        ),
        (
            "Observações",
            {"fields": (("observacao",),)},
        ),
        # (
        #     "Produtos",
        #     {"fields": (("os_related_aplicacao",),)},
        # ),
    ]


@admin.register(CondicoesMeteorologicas)
class CondicoesMeteorologicasAdmin(admin.ModelAdmin):
    list_display = ("os", "temperatura_inicial", "temperatura_final")


@admin.register(TempoAplicacao)
class TempoAplicacaoAdmin(admin.ModelAdmin):
    list_display = ("os", "inicio_aplicacao", "final_aplicacao")


@admin.register(AplicacaoAviao)
class AplicacaoAviaoAdmin(admin.ModelAdmin):
    list_display = ("os", "defensivo", "dose", "ativo")


@admin.register(TabelaPilotos)
class TabelaPilotosAdmin(admin.ModelAdmin):
    list_display = ("safra", "ciclo", "vazao", "preco", "ativo")
