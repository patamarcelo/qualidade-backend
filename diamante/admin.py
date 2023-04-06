from django.contrib import admin
from django import forms

from django.utils.formats import date_format

# Register your models here.
from django.contrib import admin
from .models import (
    Deposito,
    Fazenda,
    Projeto,
    Talhao,
    Cultura,
    Variedade,
    Safra,
    Ciclo,
    Plantio,
    Colheita,
)

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
        "variedade__variedade",
        "finalizado_plantio",
        "finalizado_colheita",
        "area_colheita",
        "area_parcial",
        "data_plantio",
    ]
    raw_id_fields = ["talhao"]
    list_display = (
        "talhao_description",
        "safra_description",
        "variedade",
        "finalizado_plantio",
        "finalizado_colheita",
        "area_colheita",
        "area_parcial",
        "get_data",
    )
    ordering = ("data_plantio",)
    
    def get_data(self,obj):
        return date_format(obj.data_plantio, format='SHORT_DATE_FORMAT', use_l10n=True)
    get_data.short_description = 'Data Plantio'

    def safra_description(self, obj):
        return f"{obj.safra.safra} - {obj.ciclo.ciclo}"
        safra_description.short_description = "Safra"

    def talhao_description(self, obj):
        projeto_name = "Projeto"
        if projeto_name in obj.talhao.fazenda.nome:
            return f'{obj.talhao.fazenda.nome.split(projeto_name)[-1]} - {obj.talhao.id_talhao}'
        else:
            return obj.talhao


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
