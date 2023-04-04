from django.contrib import admin
from django import forms

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
    # list_select_related = ["fazenda", "talhao"]
    raw_id_fields = ["talhao"]
    list_display = (
        "safra_description",
        "talhao",
        "variedade",
        "finalizado_plantio",
        "finalizado_colheita",
        "area_colheita",
        "area_parcial",
        "data_plantio",
    )
    ordering = ("data_plantio",)

    def safra_description(self, obj):
        return obj.safra.safra
        safra_description.short_description = "Safra"




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
