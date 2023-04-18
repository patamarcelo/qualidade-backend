from django.contrib import admin
from django import forms

from django.utils.formats import date_format
from django.utils.html import format_html


# Register your models here.
from django.contrib import admin
from .models import *

# admin.site.register(ValuRisk)


@admin.register(Deposito)
class DepositoAdmin(admin.ModelAdmin):
    list_display = ("nome", "id_d")
    ordering = ("nome",)


@admin.register(Fazenda)
class FazendaAdmin(admin.ModelAdmin):
    list_display = ("nome", "id_d")
    ordering = ("nome",)


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "id_d",
        "fazenda",
        "quantidade_area_produtiva",
        "quantidade_area_total",
    )
    ordering = ("nome",)


@admin.register(Talhao)
class TalhaoAdmin(admin.ModelAdmin):
    list_display = ("id_talhao", "fazenda", "id_unico", "area_total", "modulo")
    ordering = ("id_talhao",)
    search_fields = ["id_talhao", "id_unico", "area_total", "modulo"]


@admin.register(Cultura)
class CulturaAdmin(admin.ModelAdmin):
    list_display = ("cultura", "tipo_producao")
    ordering = ("cultura",)


@admin.register(Variedade)
class VariedadeAdmin(admin.ModelAdmin):
    list_display = (
        "variedade",
        "nome_fantasia",
        "cultura",
        "dias_ciclo",
        "dias_germinacao",
    )
    ordering = ("variedade",)


admin.site.register(Safra)
admin.site.register(Ciclo)


@admin.register(Plantio)
class PlantioAdmin(admin.ModelAdmin):
    search_fields = [
        "safra__safra",
        "talhao__id_unico",
        "talhao__fazenda__nome",
        "variedade__variedade",
        "finalizado_plantio",
        "finalizado_colheita",
        "area_colheita",
        "area_parcial",
        "data_plantio",
    ]
    raw_id_fields = ["talhao"]
    list_filter = (
        "variedade",
        "finalizado_colheita",
        "talhao__fazenda__nome",
        "safra__safra",
    )
    list_display = (
        "talhao",
        "safra_description",
        "variedade_description",
        "get_description_finalizado_plantio",
        "get_description_finalizado_colheita",
        "area_aproveito",
        "area_colheita",
        "area_parcial",
        "get_data",
        "get_dap_description",
        "programa",
    )
    readonly_fields = ("get_cronograma_programa",)

    ordering = ("data_plantio",)

    def get_dap_description(self, obj):
        return obj.get_dap

    get_dap_description.short_description = "DAP"

    def get_description_finalizado_plantio(self, obj):
        return obj.finalizado_plantio

    get_description_finalizado_plantio.boolean = True
    get_description_finalizado_plantio.short_description = "Plantio"

    def get_description_finalizado_colheita(self, obj):
        return obj.finalizado_colheita

    get_description_finalizado_colheita.boolean = True
    get_description_finalizado_colheita.short_description = "Colheita"

    def get_data(self, obj):
        return date_format(obj.data_plantio, format="SHORT_DATE_FORMAT", use_l10n=True)

    get_data.short_description = "Data Plantio"

    def variedade_description(self, obj):
        variedade = obj.variedade.nome_fantasia if obj.variedade.nome_fantasia else "-"
        return variedade

    variedade_description.short_description = "Variedade"

    def safra_description(self, obj):
        return f"{obj.safra.safra} - {obj.ciclo.ciclo}"

    safra_description.short_description = "Safra"

    # def talhao_description(self, obj):
    #     projeto_name = "Projeto"
    #     if projeto_name in obj.talhao.fazenda.nome:
    #         return f'{obj.talhao.fazenda.nome.split(projeto_name)[-1]} - {obj.talhao.id_talhao}'
    #     else:
    #         return obj.talhao
    # talhao_description.short_description = "Parcela"


@admin.register(Colheita)
class ColheitaAdmin(admin.ModelAdmin):
    list_display = (
        "talhao_description",
        "data_colheita",
        "romaneio",
        "placa",
        "motorista",
        "peso_umido",
        "peso_liquido",
        "deposito",
    )

    ordering = ("data_colheita",)

    def talhao_description(self, obj):
        return obj.plantio.talhao.id_talhao
        talhao_description.short_description = "Talhao"

    def deposito_abrev(self, obj):
        if "(" in obj.deposito.nome or ")" in obj.deposito.nome:
            return obj.deposito.nome.replace("(", "").replace(")", "")
        else:
            return obj.deposito.nome

    deposito_abrev.short_description = "CPF/CNPJ"


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ("nome", "safra_description")

    ordering = ("safra", "ciclo")

    def safra_description(self, obj):
        return f"{obj.safra.safra} - {obj.ciclo.ciclo}"

    safra_description.short_description = "Safra"


@admin.register(Operacao)
class OperacaoAdmin(admin.ModelAdmin):
    list_display = ("programa", "estagio", "prazo_dap", "get_cultura_description", "get_obs_description")
    list_filter = ["programa",'programa__safra','programa__ciclo']

    ordering = (
        "programa",
        "prazo_dap",
    )

    def get_cultura_description(self, obj):
        return obj.programa.cultura.cultura

    get_cultura_description.short_description = "Cultura"
    
    def get_obs_description(self, obj):
        if obj.obs:
            return f'{obj.obs[:20] }...'
        else:
            return ' - '

    get_obs_description.short_description = "Obs"


@admin.register(Defensivo)
class DefensivoAdmin(admin.ModelAdmin):
    list_display = ("produto", "tipo")
    ordering = ["produto"]
    search_fields = ["produto", "tipo"]
    list_filter = ("tipo",)


@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    list_display = ("operacao", "defensivo", "dose")
    search_fields = ["operacao", "defensivo", "dose"]
    raw_id_fields = ["operacao"]
    list_filter = ("defensivo","operacao__programa","operacao")
