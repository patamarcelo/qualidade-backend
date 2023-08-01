from django.contrib import admin
from django import forms

from django.utils.formats import date_format
from django.utils.html import format_html


# Register your models here.
from django.contrib import admin
from .models import *

import json
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe


from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.detail import DetailView
from django.urls import path, reverse

from django_json_widget.widgets import JSONEditorWidget

import csv
from django.http import HttpResponse


# class PlantioDetailView(LoginRequiredMixin, DetailView):
#     login_url = "/login/"
#     redirect_field_name = "/"
#     template_name = "admin/calendar.html"
#     model = Plantio

#     def get_context_data(self, **kwargs):
#         return {
#             **super().get_context_data(**kwargs),
#             **admin.site.each_context(self.request),
#             "opts": self.model._meta,
#         }


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename={}.csv".format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected"


class EstagiosProgramaInline(admin.StackedInline):
    model = Operacao
    extra = 0


class AplicacoesProgramaInline(admin.StackedInline):
    model = Aplicacao
    extra = 0
    fields = ["defensivo", "dose", "ativo"]


@admin.register(Deposito)
class DepositoAdmin(admin.ModelAdmin):
    list_display = ("nome", "id_d")
    ordering = ("nome",)


@admin.register(Fazenda)
class FazendaAdmin(admin.ModelAdmin):
    list_display = ("nome", "id_d", "get_plantio_dia")
    ordering = ("nome",)
    show_full_result_count = False

    def get_plantio_dia(self, obj):
        return f"{obj.capacidade_plantio_ha_dia} ha/dia"

    get_plantio_dia.short_description = "Plantio / Dia"


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return (
            super(ProjetoAdmin, self)
            .get_queryset(request)
            .select_related(
                "fazenda",
            )
        )

    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="50vh", mode="tree")
        },
    }
    show_full_result_count = False
    list_display = (
        "nome",
        "id_d",
        "fazenda",
        "quantidade_area_produtiva",
        "quantidade_area_total",
        "get_map_centro_id",
    )

    search_fields = ["fazenda__nome"]

    list_filter = (("map_centro_id", admin.EmptyFieldListFilter),)

    def get_map_centro_id(self, obj):
        if obj.map_centro_id:
            return True
        return False

    get_map_centro_id.boolean = True
    get_map_centro_id.short_description = "MAP ID"
    ordering = ("nome",)


@admin.register(Talhao)
class TalhaoAdmin(admin.ModelAdmin):
    list_display = ("id_talhao", "fazenda", "id_unico", "area_total", "modulo")
    ordering = ("id_talhao",)
    search_fields = ["id_talhao", "id_unico", "area_total", "modulo", "fazenda__nome"]


@admin.register(Cultura)
class CulturaAdmin(admin.ModelAdmin):
    list_display = ("cultura", "tipo_producao")
    ordering = ("cultura",)


@admin.register(Variedade)
class VariedadeAdmin(admin.ModelAdmin):
    show_full_result_count = False

    list_display = (
        "variedade",
        "nome_fantasia",
        "cultura",
        "dias_ciclo",
        "dias_germinacao",
    )
    ordering = ("variedade",)
    list_filter = [
        "cultura",
    ]


admin.site.register(Safra)
admin.site.register(Ciclo)


@admin.register(Plantio)
class PlantioAdmin(admin.ModelAdmin, ExportCsvMixin):
    actions = ["export_as_csv"]
    show_full_result_count = False

    def get_ordering(self, request):
        return ["data_plantio"]

    def get_queryset(self, request):
        return (
            super(PlantioAdmin, self)
            .get_queryset(request)
            .select_related(
                "talhao",
                "safra",
                "ciclo",
                "talhao__fazenda",
                "variedade",
                "programa",
            )
            .order_by("data_plantio")
        )

    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="100vh", mode="tree")
        },
    }
    search_fields = [
        "safra__safra",
        "talhao__id_unico",
        "talhao__fazenda__nome",
        "talhao__fazenda__fazenda__nome",
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
        "finalizado_plantio",
        "finalizado_colheita",
        "talhao__fazenda__nome",
        "safra__safra",
        "ciclo__ciclo",
        "programa__nome",
        "modificado",
    )
    list_display = (
        "talhao",
        "safra_description",
        "variedade_description",
        "get_description_finalizado_plantio",
        "get_description_finalizado_colheita",
        "area_colheita",
        # "area_parcial",
        "get_data",
        "get_dap_description",
        "get_dias_ciclo",
        "programa",
        # "detail",
    )

    # def get_urls(self):
    #     return [
    #         path(
    #             "<pk>/detail",
    #             self.admin_site.admin_view(PlantioDetailView.as_view()),
    #             name=f"products_order_detail",
    #         ),
    #         *super().get_urls(),
    #     ]

    # def detail(self, obj: Plantio) -> str:
    #     url = reverse("admin:products_order_detail", args=[obj.pk])
    #     return format_html(f'<a href="{url}">📝</a>')

    fieldsets = (
        (
            "Dados",
            {
                "fields": (
                    ("get_data_plantio", "get_dap_description", "get_talhao__id_unico"),
                    (
                        "talhao",
                        "ativo",
                    ),
                    ("criados", "modificado"),
                )
            },
        ),
        (
            "Plantio",
            {
                "fields": (
                    ("area_colheita",),
                    ("safra", "ciclo"),
                    ("variedade", "programa"),
                    (
                        "finalizado_plantio",
                        "data_prevista_plantio",
                    ),
                    (
                        "data_plantio",
                        "data_emergencia",
                    ),
                    (
                        "finalizado_colheita",
                        "data_prevista_colheita",
                    ),
                    ("plantio_descontinuado",),
                )
            },
        ),
        ("Programa", {"fields": ("cronograma_programa",)}),
        ("Display Map", {"fields": ("map_centro_id", "map_geo_points")}),
        ("Cronograma Previsto", {"fields": ("get_cronograma_programa",)}),
    )
    readonly_fields = (
        "get_cronograma_programa",
        "criados",
        "modificado",
        "get_dap_description",
        "get_data_plantio",
        "get_talhao__id_unico",
    )

    ordering = ("data_plantio",)

    def get_talhao__id_unico(self, obj):
        return obj.talhao.id_unico

    get_talhao__id_unico.short_description = "ID Talhao"

    def get_cronograma_programa(self, obj=None):
        result = ""
        if obj and obj.get_cronograma_programa:
            result = json.dumps(
                obj.get_cronograma_programa,
                indent=4,
                sort_keys=True,
                cls=DjangoJSONEncoder,
            )
            # keep spaces
            result_str = f"<pre>{result}</pre>"
            result = mark_safe(result_str)
        return result

    get_cronograma_programa.short_description = "Programações"

    def get_data_plantio(self, obj):
        if obj.data_plantio:
            return date_format(
                obj.data_plantio, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data_plantio.short_description = "Data Plantio "

    def get_dias_ciclo(self, obj):
        if obj.variedade:
            return obj.variedade.dias_ciclo
        else:
            return "Não Planejado"

    get_dias_ciclo.short_description = "Ciclo "

    def get_dap_description(self, obj):
        return obj.get_dap

    get_dap_description.short_description = "DAP "

    def get_description_finalizado_plantio(self, obj):
        return obj.finalizado_plantio

    get_description_finalizado_plantio.boolean = True
    get_description_finalizado_plantio.short_description = "Plantio"

    def get_description_finalizado_colheita(self, obj):
        return obj.finalizado_colheita

    get_description_finalizado_colheita.boolean = True
    get_description_finalizado_colheita.short_description = "Colheita"

    def get_data(self, obj):
        if obj.data_plantio:
            return date_format(
                obj.data_plantio, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data.short_description = "Data Plantio"

    def variedade_description(self, obj):
        if obj.variedade:
            variedade = (
                obj.variedade.nome_fantasia if obj.variedade.nome_fantasia else "-"
            )
        else:
            variedade = "Não Planejado"
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
    def get_queryset(self, request):
        return (
            super(ColheitaAdmin, self)
            .get_queryset(request)
            .select_related(
                "plantio", "deposito", "plantio__talhao", "plantio__talhao__fazenda"
            )
        )

    fieldsets = (
        (
            "Dados",
            {
                "fields": (
                    ("ativo",),
                    ("criados", "modificado"),
                )
            },
        ),
        (
            "Carga",
            {
                "fields": (
                    # ("get_projeto_origem", "get_projeto_parcela", "get_nome_fantasia"),
                    ("plantio",),
                    ("data_colheita",),
                    ("placa", "motorista"),
                    ("ticket", "op"),
                    ("peso_bruto", "peso_tara"),
                    ("peso_liquido", "peso_scs_liquido"),
                )
            },
        ),
        (
            "Descontos",
            {
                "fields": (
                    ("umidade", "desconto_umidade"),
                    ("impureza", "desconto_impureza"),
                )
            },
        ),
    )

    list_display = (
        "romaneio",
        "get_data_colheita",
        "get_placa",
        "get_nome_motorista",
        "get_projeto_origem",
        "get_projeto_parcela",
        "get_nome_fantasia",
        "ticket",
        "op",
        "peso_bruto",
        "peso_tara",
        "umidade",
        "desconto_umidade",
        "impureza",
        "desconto_impureza",
        "peso_liquido",
        "peso_scs_liquido",
    )

    raw_id_fields = ["plantio"]

    readonly_fields = (
        "peso_liquido",
        "peso_scs_liquido",
        "desconto_umidade",
        "desconto_impureza",
        "criados",
        "modificado",
    )

    ordering = ("data_colheita",)

    def get_data_colheita(self, obj):
        if obj.data_colheita:
            return date_format(
                obj.data_colheita, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data_colheita.short_description = "Data"

    def get_nome_fantasia(self, obj):
        return obj.deposito.nome_fantasia

    get_nome_fantasia.short_description = "Depósito"

    def get_nome_motorista(self, obj):
        return obj.motorista.upper()

    get_nome_motorista.short_description = "Motorista"

    def get_placa(self, obj):
        return f"{obj.placa[0:3]}-{obj.placa[3:]}"

    get_placa.short_description = "Placa"

    def get_projeto_origem(self, obj):
        return obj.plantio.talhao.fazenda.nome

    get_projeto_origem.short_description = "Origem"

    def get_projeto_parcela(self, obj):
        return obj.plantio.talhao.id_talhao

    get_projeto_parcela.short_description = "Parcela"

    # def talhao_description(self, obj):
    #     return obj.plantio.talhao.id_talhao
    #     talhao_description.short_description = "Talhao"

    # def deposito_abrev(self, obj):
    #     if "(" in obj.deposito.nome or ")" in obj.deposito.nome:
    #         return obj.deposito.nome.replace("(", "").replace(")", "")
    #     else:
    #         return obj.deposito.nome

    # deposito_abrev.short_description = "CPF/CNPJ"


@admin.register(Programa)
class ProgramaAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return (
            super(ProgramaAdmin, self)
            .get_queryset(request)
            .select_related("safra", "ciclo")
        )

    show_full_result_count = False

    inlines = [EstagiosProgramaInline]
    list_display = (
        "nome",
        "safra_description",
        "start_date_description",
        "end_date_description",
    )

    ordering = ("safra", "ciclo")

    def safra_description(self, obj):
        return f"{obj.safra.safra} - {obj.ciclo.ciclo}"

    safra_description.short_description = "Safra"

    def start_date_description(self, obj):
        if obj.start_date:
            return date_format(
                obj.start_date, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    start_date_description.short_description = "Start Plantio"

    def end_date_description(self, obj):
        if obj.end_date:
            return date_format(obj.end_date, format="SHORT_DATE_FORMAT", use_l10n=True)
        else:
            return " - "

    end_date_description.short_description = "End Plantio"


@admin.register(Operacao)
class OperacaoAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return (
            super(OperacaoAdmin, self)
            .get_queryset(request)
            .select_related("programa", "programa__cultura")
        )

    show_full_result_count = False

    search_fields = [
        "programa__nome",
        "programa__nome_fantasia",
        "programa__cultura__cultura",
        "estagio",
        "prazo_dap",
        "obs",
    ]

    inlines = [AplicacoesProgramaInline]
    list_display = (
        "programa",
        "estagio",
        "prazo_dap",
        "get_cultura_description",
        "get_obs_description",
    )
    list_filter = ["programa", "programa__safra", "programa__ciclo"]

    ordering = (
        "programa",
        "prazo_dap",
    )

    def get_cultura_description(self, obj):
        return obj.programa.cultura.cultura

    get_cultura_description.short_description = "Cultura"

    def get_obs_description(self, obj):
        if obj.obs:
            return f"{obj.obs[:20] }..."
        else:
            return " - "

    get_obs_description.short_description = "Obs"


@admin.register(Defensivo)
class DefensivoAdmin(admin.ModelAdmin):
    list_display = ("produto", "tipo")
    ordering = ["produto"]
    search_fields = ["produto", "tipo"]
    list_filter = ("tipo",)
    show_full_result_count = False


@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return (
            super(AplicacaoAdmin, self)
            .get_queryset(request)
            .select_related("operacao", "defensivo", "operacao__programa")
        )

    show_full_result_count = False

    list_display = (
        "operacao",
        "programa",
        "defensivo",
        "defensivo__formulacao",
        "dose",
        "get_operacao_prazo_dap",
        "ativo",
    )
    search_fields = [
        "operacao__programa__nome",
        "operacao__estagio",
        "defensivo__produto",
        "dose",
    ]
    raw_id_fields = ["operacao"]
    list_filter = (
        "defensivo",
        "operacao__programa",
        "operacao",
        "defensivo__tipo",
        "ativo",
    )

    readonly_fields = (
        "criados",
        "modificado",
    )

    def defensivo__formulacao(self, obj):
        return obj.defensivo.get_tipo_display()

    defensivo__formulacao.short_description = "Tipo"

    def get_operacao_prazo_dap(self, obj):
        return obj.operacao.prazo_dap

    get_operacao_prazo_dap.short_description = "DAP"

    def programa(self, obj):
        return obj.operacao.programa

    programa.short_description = "Programa"
