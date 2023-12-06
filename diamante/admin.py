from typing import Any
from django.contrib import admin
from django import forms
from django.db.models.query import QuerySet
from django.http.request import HttpRequest

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
import codecs

from django.db.models import Q, Sum, F

from django.db.models import Subquery, OuterRef
from django.utils.formats import localize


from django.db.models import Case, When, DecimalField, Value
from django.db.models.functions import Coalesce, Round

from django.core import serializers
from django.contrib.admin import SimpleListFilter
from datetime import datetime, timedelta

from django.contrib import messages


from admin_extra_buttons.api import (
    ExtraButtonsMixin,
    button,
    confirm_action,
    link,
    view,
)
from admin_extra_buttons.utils import HttpResponseRedirectToReferrer
from django.http import HttpResponse, JsonResponse
from django.contrib import admin
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from .utils import (
    admin_form_alter_programa_and_save,
    admin_form_remove_index,
    close_plantation_and_productivity,
)


def get_cargas_model(safra_filter, ciclo_filter):
    cargas_model = [
        x
        for x in Colheita.objects.values(
            "plantio__talhao__fazenda__nome",
            "plantio__variedade__cultura__cultura",
            "plantio__variedade__variedade",
        )
        .annotate(
            peso_kg=Sum(F("peso_liquido") * 60),
            peso_scs=Round((Sum("peso_scs_limpo_e_seco")), precision=2),
        )
        .order_by("plantio__talhao__fazenda__nome")
        .filter(~Q(plantio__variedade__cultura__cultura="Milheto"))
        .filter(plantio__safra__safra=safra_filter, plantio__ciclo=ciclo_filter)
    ]
    return cargas_model


@admin.register(PlantioDetail)
class PlantioDetailAdmin(admin.ModelAdmin):
    model = PlantioDetail
    change_list_template = "admin/custom_temp.html"

    # cargas_model = [
    #     x
    #     for x in Colheita.objects.values(
    #         "plantio__talhao__id_talhao", "plantio__id", "peso_liquido", "data_colheita"
    #     )
    # ]
    cicle_filter = None

    def get_queryset(self, request):
        global cicle_filter
        request.GET = request.GET.copy()
        ciclo = request.GET.pop("ciclo", None)
        if ciclo:
            ciclo_index = int(ciclo[0]) - 1
            cicle_filter = Ciclo.objects.all()[ciclo_index]
            return (
                super(PlantioDetailAdmin, self)
                .get_queryset(request)
                .select_related(
                    "talhao",
                    "safra",
                    "ciclo",
                    "talhao__fazenda",
                    "variedade",
                    "programa",
                )
                .filter(ciclo=cicle_filter)
                .order_by("data_plantio")
            )
        else:
            cicle_filter = Ciclo.objects.all()[1]
        return (
            super(PlantioDetailAdmin, self)
            .get_queryset(request)
            .select_related(
                "talhao",
                "safra",
                "ciclo",
                "talhao__fazenda",
                "variedade",
                "programa",
            )
            .filter(ciclo=cicle_filter)
            .order_by("data_plantio")
        )

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        safra_filter = "2023/2024"

        # ciclo_filter = "1"
        # cicle_filter = Ciclo.objects.all()[0]
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        metrics = {
            "area_total": Sum("area_colheita"),
            "area_finalizada": Case(
                When(finalizado_colheita=True, then=Coalesce(Sum("area_colheita"), 0)),
                When(finalizado_colheita=False, then=Coalesce(Sum("area_parcial"), 0)),
                default=Value(0),
                output_field=DecimalField(),
                # ),
                # "area_parcial": Case(
                #     When(finalizado_colheita=False, then=Coalesce(Sum("area_parcial"), 0)),
                #     default=Value(0),
                #     output_field=DecimalField(),
            ),
        }

        query_data = (
            qs.filter(
                safra__safra=safra_filter,
                ciclo=cicle_filter,
                finalizado_plantio=True,
                plantio_descontinuado=False,
            )
            .filter(~Q(variedade__cultura__cultura="Milheto"))
            # .filter(~Q(talhao__fazenda__nome="Projeto Lago Verde"))
            .values(
                "talhao__fazenda__nome",
                "variedade__cultura__cultura",
                "variedade__variedade",
            )
            .annotate(**metrics)
            .order_by("talhao__fazenda__nome")
        )

        response.context_data["summary_2"] = json.dumps(
            list(query_data), cls=DjangoJSONEncoder
        )

        response.context_data["colheita_2"] = json.dumps(
            get_cargas_model(safra_filter, cicle_filter), cls=DjangoJSONEncoder
        )

        return response


@admin.register(PlantioDetailPlantio)
class PlantioDetailPlantioAdmin(admin.ModelAdmin):
    model = PlantioDetailPlantio
    change_list_template = "admin/custom_temp_plantio.html"

    # cargas_model = [
    #     x
    #     for x in Colheita.objects.values(
    #         "plantio__talhao__id_talhao", "plantio__id", "peso_liquido", "data_colheita"
    #     )
    # ]
    cicle_filter = None

    def get_queryset(self, request):
        global cicle_filter
        request.GET = request.GET.copy()
        ciclo = request.GET.pop("ciclo", None)
        if ciclo:
            ciclo_index = int(ciclo[0]) - 1
            cicle_filter = Ciclo.objects.all()[ciclo_index]
            return (
                super(PlantioDetailPlantioAdmin, self)
                .get_queryset(request)
                .select_related(
                    "talhao",
                    "safra",
                    "ciclo",
                    "talhao__fazenda",
                    "variedade",
                    "programa",
                )
                .filter(ciclo=cicle_filter)
                .order_by("data_plantio")
            )
        else:
            cicle_filter = Ciclo.objects.all()[1]
        return (
            super(PlantioDetailPlantioAdmin, self)
            .get_queryset(request)
            .select_related(
                "talhao",
                "safra",
                "ciclo",
                "talhao__fazenda",
                "variedade",
                "programa",
            )
            .filter(ciclo=cicle_filter)
            .order_by("data_plantio")
        )

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        safra_filter = "2023/2024"
        # ciclo_filter = "2"
        # ciclo_filter = request.GET["ciclo"]
        # print(ciclo_filter)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        metrics = {
            "area_total": Sum("area_colheita"),
            "area_plantada": Case(
                When(finalizado_plantio=True, then=Coalesce(Sum("area_colheita"), 0)),
                default=Value(0),
                output_field=DecimalField(),
            ),
            "area_projetada": Case(
                When(finalizado_plantio=False, then=Coalesce(Sum("area_colheita"), 0)),
                default=Value(0),
                output_field=DecimalField(),
                # ),
                # "area_parcial": Case(
                #     When(finalizado_colheita=False, then=Coalesce(Sum("area_parcial"), 0)),
                #     default=Value(0),
                #     output_field=DecimalField(),
            ),
        }
        query_data = (
            qs.filter(
                safra__safra=safra_filter,
                plantio_descontinuado=False,
            )
            .filter(~Q(variedade__cultura__cultura="Milheto"))
            .filter(~Q(variedade=None))
            .values(
                "talhao__fazenda__nome",
                "variedade__cultura__cultura",
                "variedade__variedade",
                "finalizado_plantio",
            )
            .annotate(**metrics)
            .order_by("talhao__fazenda__nome")
        )

        response.context_data["summary_2"] = json.dumps(
            list(query_data), cls=DjangoJSONEncoder
        )

        response.context_data["colheita_2"] = json.dumps(
            get_cargas_model(safra_filter, cicle_filter), cls=DjangoJSONEncoder
        )

        return response


# --------------------------- DELETAR SE NÃO FIZER FALTA - 18/10/2023 ---------------------------#
# class ExportCsvMixin:
#     def export_as_csv(self, request, queryset):
#         meta = self.model._meta
#         field_names = [field.name for field in meta.fields]
#         response = HttpResponse(content_type="text/csv")
#         response["Content-Disposition"] = "attachment; filename={}.csv".format(meta)
#         writer = csv.writer(response)

#         writer.writerow(field_names)
#         for obj in queryset:
#             row = writer.writerow([getattr(obj, field) for field in field_names])

#         return response

#     export_as_csv.short_description = "Export Selected"
# --------------------------- DELETAR SE NÃO FIZER FALTA - 18/10/2023 ---------------------------#


class EstagiosProgramaInline(admin.StackedInline):
    model = Operacao
    extra = 0
    fields = ["ativo", "estagio", "operacao_numero", "prazo_dap"]


class AplicacoesProgramaInline(admin.StackedInline):
    model = Aplicacao
    extra = 0
    fields = ["defensivo", "dose", "ativo"]
    autocomplete_fields = ["defensivo"]


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
    search_fields = ["variedade"]


admin.site.register(Safra)
admin.site.register(Ciclo)


def export_plantio(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="Plantio.csv"'
    response.write(codecs.BOM_UTF8)
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Fazenda",
            "Projeto",
            "Talhao",
            "Safra",
            "Ciclo",
            "Cultura",
            "Variedade",
            "Plantio Finalizado",
            "Colheita Finalizada",
            "Area",
            "Data Plantio",
            "Data Prev Colheita",
            # "Dap",
            "Ciclo Variedade",
            "Programa",
            "Cargas Carregadas",
            "Carregado Kg",
            "Produtividade",
            "lat",
            "long",
        ]
    )

    plantios = queryset.values_list(
        "pk",
        "talhao__fazenda__fazenda__nome",
        "talhao__fazenda__nome",
        "talhao__id_talhao",
        "safra__safra",
        "ciclo__ciclo",
        "variedade__cultura__cultura",
        "variedade__variedade",
        "finalizado_plantio",
        "finalizado_colheita",
        "area_colheita",
        "data_plantio",
        "variedade__dias_ciclo",
        "programa__nome",
        "area_parcial",
        "map_centro_id",
    )
    cargas_list = modeladmin.total_c_2

    def get_total_prod(total_c_2, plantio):
        total_filt_list = sum([(x[1] * 60) for x in total_c_2 if plantio[0] == x[0]])
        prod_scs = None
        if plantio[8]:
            try:
                prod = total_filt_list / plantio[10]
                prod_scs = prod / 60
            except ZeroDivisionError:
                value = float("Inf")
        if plantio[14]:
            try:
                if plantio[13].isdecimal():
                    prod = total_filt_list / plantio[13]
                    prod_scs = prod / 60
            except ZeroDivisionError:
                value = float("Inf")
        if prod_scs:
            return localize(round(prod_scs, 2))
        else:
            return " - "

    def get_prev_colheita(data_plantio, timeDelta):
        if data_plantio:
            prev_date_delta = timedelta(timeDelta)
            prev_date_final = data_plantio + prev_date_delta
            return prev_date_final
        else:
            return " - "

    for plantio in plantios:
        plantio_detail = list(plantio)
        lat = str(plantio_detail[15]["lat"]).replace(".", ",")
        lng = str(plantio_detail[15]["lng"]).replace(".", ",")
        plantio_detail.pop(15)
        data_plantio = plantio_detail[11]
        time_delta_plantio = plantio_detail[12]
        plantio_detail[10] = localize(plantio_detail[10])
        cargas_carregadas_filter = [
            (x[1] * 60) for x in cargas_list if plantio_detail[0] == x[0]
        ]
        cargas_carregadas_kg = localize(sum(cargas_carregadas_filter))
        cargas_carregadas_quantidade = len(cargas_carregadas_filter)
        produtividade = get_total_prod(cargas_list, plantio)
        plantio_detail.pop(14)
        plantio_detail.append(cargas_carregadas_quantidade)
        plantio_detail.append(cargas_carregadas_kg)
        plantio_detail.append(produtividade)
        plantio_detail.append(lat)
        plantio_detail.append(lng)
        plantio_detail.pop(0)
        plantio_detail.insert(11, get_prev_colheita(data_plantio, time_delta_plantio))
        print(plantio_detail)
        print(lat, lng)
        plantio = tuple(plantio_detail)
        writer.writerow(plantio)
    return response


def get_cargas_colheita():
    total_c_2 = [
        x
        for x in Colheita.objects.values_list(
            "plantio__id", "peso_liquido", "data_colheita"
        )
    ]
    return total_c_2


class ColheitaFilter(SimpleListFilter):
    title = "Cargas"  # or use _('country') for translated title
    parameter_name = "cargas"

    def lookups(self, request, model_admin):
        # id_list = [x['plantio__id'] for x in model_admin.total_c_2]
        # filtered_query = model_admin.model.objects.filter(id__in=id_list)
        # return filtered_query
        return [
            ("Carregados", "Carregados"),
            ("Sem Cargas", "Sem Cargas"),
        ]

    def queryset(self, request, queryset):
        id_list = [x[0] for x in get_cargas_colheita()]
        if self.value() == "Carregados":
            return queryset.filter(id__in=id_list)
        if self.value() == "Sem Cargas":
            return queryset.exclude(id__in=id_list)


class ColheitaFilterNoProgram(SimpleListFilter):
    title = "Sem Programa"  # or use _('country') for translated title
    parameter_name = "programas"

    def lookups(self, request, model_admin):
        return [
            ("Com Programa", "Programa"),
            ("Sem Programa", "Sem Programa"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "Programa":
            return queryset.filter(~Q(programa_id=None))
        if self.value() == "Sem Programa":
            return queryset.filter(Q(programa_id=None))


@admin.register(Plantio)
class PlantioAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    actions = [export_plantio]
    show_full_result_count = False
    autocomplete_fields = ["talhao", "programa", "variedade"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_c_2 = [
            x
            for x in Colheita.objects.values_list(
                "plantio__id", "peso_scs_limpo_e_seco", "data_colheita"
            )
        ]

    @button(
        change_form=True,
        html_attrs={
            "class": "btn btn-outline-info btn-sm",
        },
    )
    def atualizar_colheita(self, request):
        self.message_user(request, "Dados da Colheita Atualizado")
        self.total_c_2 = [
            x
            for x in Colheita.objects.values_list(
                "plantio__id", "peso_scs_limpo_e_seco", "data_colheita"
            )
        ]
        return HttpResponseRedirectToReferrer(request)

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
                "variedade__cultura",
                "programa",
            )
        )

    def get_search_results(self, request, queryset, search_term):
        ciclo_filter = CicloAtual.objects.filter(nome="Colheita")[0]
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )

        # Exclude only for autocomplete
        print("resquest_Path", request.path)

        if request.path == "/admin/autocomplete/":
            queryset = queryset.filter(
                ciclo=ciclo_filter.ciclo,
                finalizado_colheita=False,
                plantio_descontinuado=False,
            )

        return queryset, use_distinct

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
        "variedade__cultura__cultura",
        "finalizado_plantio",
        "finalizado_colheita",
        "area_colheita",
        "area_parcial",
        "data_plantio",
    ]
    raw_id_fields = ["talhao"]
    list_filter = (
        "safra__safra",
        "ciclo__ciclo",
        "variedade__cultura",
        ColheitaFilter,
        ColheitaFilterNoProgram,
        "finalizado_plantio",
        "finalizado_colheita",
        "plantio_descontinuado",
        "programa__nome",
        # "talhao__fazenda__nome",
        "variedade",
        "modificado",
    )
    list_display = (
        "talhao",
        "cultura_description",
        "variedade_description",
        "safra_description",
        "programa",
        "get_description_finalizado_plantio",
        "get_data",
        "get_data_prev_col",
        "area_colheita",
        "get_description_finalizado_colheita",
        # "get_area_parcial",
        "get_total_colheita_cargas_kg",
        # "talhao",
        "get_total_prod",
        "get_data_primeira_carga",
        "get_data_ultima_carga",
        "get_total_colheita_cargas",
        # "area_parcial",
        "get_dap_description",
        "get_dias_ciclo",
        "get_description_descontinuado_plantio",
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
                    (
                        "get_data_plantio",
                        "get_dap_description",
                        "get_talhao__id_unico",
                        "id_farmbox",
                    ),
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
                    ("data_prevista_colheita",),
                    (
                        "area_parcial",
                        "finalizado_colheita",
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
        "id_farmbox",
    )

    def save_model(self, request, obj, form, change):
        print(obj)
        print(self)
        print("form Plantio")
        print("Valor Atual: ")
        if form.initial:
            if form.initial["data_plantio"] != obj.data_plantio:
                obj.cronograma_programa = None
            if (
                form.initial["finalizado_colheita"] == False
                and form.instance.finalizado_colheita == True
            ):
                print("Colheita Finalizada")

                # GET CLOSED DATE
                filtered_list = [x[2] for x in self.total_c_2 if obj.id == x[0]]
                sorted_list = sorted(filtered_list)
                closed_date = None
                if len(sorted_list) > 0:
                    closed_date = sorted_list[0]
                else:
                    today = str(datetime.now()).split(" ")[0].strip()
                    closed_date = today

                # GET PROD NUMBER
                total_filt_list = sum(
                    [(x[1] * 60) for x in self.total_c_2 if obj.id == x[0]]
                )
                prod_scs = None
                value = None
                if obj.finalizado_colheita:
                    try:
                        prod = total_filt_list / obj.area_colheita
                        prod_scs = prod / 60
                        value = round(prod_scs, 2)
                        print(value)
                    except ZeroDivisionError:
                        value = None

                print("Produtividade ", value)
                print("Data Colheita", closed_date)
                print("id_farmBox", obj.id_farmbox)
                try:
                    response = close_plantation_and_productivity(
                        obj.id_farmbox, str(closed_date), str(value)
                    )
                    print(response)
                    resp_obj = json.loads(response.text)
                    str_resp = f'Alterado no FARMBOX - {resp_obj["farm_name"]} - {resp_obj["name"]} - {resp_obj["harvest_name"]}-{resp_obj["cycle"]} - Produtividade: {resp_obj["productivity"]} - Variedade: {resp_obj["variety_name"]} - Area: {resp_obj["area"]}'
                    messages.add_message(request, messages.INFO, str_resp)
                except Exception as e:
                    print("Erro ao alterar os dados no FarmBox")
                    messages.add_message(
                        request,
                        messages.ERROR,
                        f"Erro ao salvar os dados no Farmbox: {e}",
                    )
        form.save()

    def get_readonly_fields(self, request, obj=None):
        if obj == None:
            return self.readonly_fields
        if obj and obj.programa is None:
            return self.readonly_fields
        if obj and obj.programa.ativo == True:
            return self.readonly_fields
        return self.readonly_fields + ("programa",)

    ordering = ("data_plantio",)

    def get_area_parcial(self, obj):
        if obj.finalizado_colheita:
            return " - "
        else:
            return obj.area_parcial

    get_area_parcial.short_description = "Area  Parcial"

    # DATA PRIMEIRA CARGA CARREGADA
    def get_data_primeira_carga(self, obj):
        filtered_list = [x[2] for x in self.total_c_2 if obj.id == x[0]]
        sorted_list = sorted(filtered_list)
        if len(sorted_list) > 0:
            return date_format(
                sorted_list[0], format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return "-"

    get_data_primeira_carga.short_description = "1ª Carga"

    # DATA ÚLTIMA CARGA CARREGADA
    def get_data_ultima_carga(self, obj):
        filtered_list = [x[2] for x in self.total_c_2 if obj.id == x[0]]
        sorted_list = sorted(filtered_list)
        if len(sorted_list) > 0:
            return date_format(
                sorted_list[-1], format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return "-"

    get_data_ultima_carga.short_description = "últ. Carga"

    # TOTAL DE CARGAS CARREGADAS PARA O PLANTIO
    def get_total_colheita_cargas(self, obj):
        filtered_list = [x[1] for x in self.total_c_2 if obj.id == x[0]]
        return len(filtered_list)

    get_total_colheita_cargas.short_description = "Cargas"

    # TOTAL DE CARGAS CARREGADAS PARA O PLANTIO E KG
    def get_total_colheita_cargas_kg(self, obj):
        filtered_list = [(x[1] * 60) for x in self.total_c_2 if obj.id == x[0]]
        return sum(filtered_list)

    get_total_colheita_cargas_kg.short_description = "Peso Carr."

    # PRODUTIVIDADE TOTAL DO PLANTIO
    def get_total_prod(self, obj):
        total_filt_list = sum([(x[1] * 60) for x in self.total_c_2 if obj.id == x[0]])
        prod_scs = None
        if obj.finalizado_colheita:
            try:
                prod = total_filt_list / obj.area_colheita
                prod_scs = prod / 60
                return f"{localize(round(prod_scs,2))} Scs/ha"
            except ZeroDivisionError:
                value = float("Inf")
        if obj.area_parcial:
            try:
                prod = total_filt_list / obj.area_parcial
                prod_scs = prod / 60
            except ZeroDivisionError:
                value = float("Inf")
        if prod_scs:
            return f"{localize(round(prod_scs,2))} Scs/ha"
        else:
            return " - "

    get_total_prod.short_description = "Produtividade"

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

    def get_description_descontinuado_plantio(self, obj):
        return obj.plantio_descontinuado

    get_description_descontinuado_plantio.boolean = True
    get_description_descontinuado_plantio.short_description = "Interrom? "

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

    def get_data_prev_col(self, obj):
        if obj.data_plantio:
            prev_date_delta = timedelta(obj.variedade.dias_ciclo)
            prev_date_final = obj.data_plantio + prev_date_delta
            return date_format(
                prev_date_final, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data_prev_col.short_description = "Data Prev. Col."

    def variedade_description(self, obj):
        if obj.variedade:
            variedade = (
                obj.variedade.nome_fantasia if obj.variedade.nome_fantasia else "-"
            )
        else:
            variedade = "Não Planejado"
        return variedade

    variedade_description.short_description = "Variedade"

    def cultura_description(self, obj):
        if obj.variedade is not None:
            cultura = (
                obj.variedade.cultura.cultura if obj.variedade.cultura.cultura else "-"
            )
            cultura_url = None
            if cultura == "Soja":
                cultura_url = "soy"
            if cultura == "Feijão":
                cultura_url = "beans2"
            if cultura == "Arroz":
                cultura_url = "rice"
            image_url = None
            if cultura_url is not None:
                image_url = f"/static/images/icons/{cultura_url}.png"
            if image_url is not None:
                return format_html(
                    f'<img style="width: 20px; height: 20px; text-align: center"  src="{image_url}">'
                )
        else:
            cultura = "Não Planejado"
        return cultura

    cultura_description.short_description = "Cultura"

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


def export_cargas(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="Cargas.csv"'
    response.write(codecs.BOM_UTF8)
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Romaneio",
            "Data",
            "Ticket",
            "OP",
            "Origem",
            "Origem - Projeto",
            "Destino",
            "Parcela",
            "Safra",
            "Ciclo",
            "Variedade",
            "Cultura",
            "Placa",
            "Motorista",
            "Peso Tara",
            "Peso Bruto",
            "Peso",
            "Umidade",
            "Desc. Umidade",
            "Impureza",
            "Desc. Impureza",
            "Limpo e Seco",
            "Bandinha",
            "Desc. Bandinha",
            "Peso Liquido",
            "Peso Líquido Scs",
        ]
    )
    cargas = queryset.values_list(
        "romaneio",
        "data_colheita",
        "ticket",
        "op",
        "plantio__talhao__fazenda__fazenda__nome",
        "plantio__talhao__fazenda__nome",
        "deposito__nome_fantasia",
        "plantio__talhao__id_talhao",
        "plantio__safra__safra",
        "plantio__ciclo__ciclo",
        "plantio__variedade__variedade",
        "plantio__variedade__cultura__cultura",
        "placa",
        "motorista",
        "peso_tara",
        "peso_bruto",
        "umidade",
        "desconto_umidade",
        "impureza",
        "desconto_impureza",
        "peso_scs_limpo_e_seco",
        "bandinha",
        "desconto_bandinha",
        "peso_liquido",
    )
    for carga in cargas:
        cargas_detail = list(carga)
        # cargas_detail[16] = str(carga[16]).replace(".", ",")
        # cargas_detail[17] = str(carga[17]).replace(".", ",")
        cargas_detail[16] = 0 if carga[16] == None else str(carga[16]).replace(".", ",")
        cargas_detail[17] = 0 if carga[17] == None else str(carga[17]).replace(".", ",")
        cargas_detail[18] = 0 if carga[18] == None else str(carga[18]).replace(".", ",")
        cargas_detail[19] = 0 if carga[19] == None else str(carga[19]).replace(".", ",")
        cargas_detail[20] = 0 if carga[20] == None else str(carga[20]).replace(".", ",")
        cargas_detail[21] = 0 if carga[21] == None else str(carga[21]).replace(".", ",")
        cargas_detail[22] = 0 if carga[22] == None else str(carga[22]).replace(".", ",")
        cargas_detail[23] = 0 if carga[23] == None else str(carga[23]).replace(".", ",")
        peso = cargas_detail[15] - cargas_detail[14]
        cargas_detail.insert(16, peso)
        cargas_detail.insert(
            25,
            str(round((float(cargas_detail[24].replace(",", ".")) / 60), 2)).replace(
                ".", ","
            ),
        )
        carga = tuple(cargas_detail)
        writer.writerow(carga)
    return response


export_cargas.short_description = "Export to csv"


@admin.register(Colheita)
class ColheitaAdmin(admin.ModelAdmin):
    autocomplete_fields = ["plantio"]

    def get_queryset(self, request):
        return (
            super(ColheitaAdmin, self)
            .get_queryset(request)
            .select_related(
                "plantio",
                "deposito",
                "plantio__talhao",
                "plantio__talhao__fazenda",
                "plantio__variedade",
                "plantio__variedade__cultura",
                "plantio__safra",
                "plantio__ciclo",
            )
        )

    actions = [
        export_cargas,
    ]
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
                    ("plantio", "deposito"),
                    ("data_colheita", "romaneio"),
                    ("placa", "motorista"),
                    ("ticket", "op"),
                    ("peso_tara", "peso_bruto"),
                    ("peso_scs_limpo_e_seco"),
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
                    ("bandinha", "desconto_bandinha"),
                )
            },
        ),
    )

    list_display = (
        "romaneio",
        "get_data_colheita",
        "get_placa",
        "get_nome_motorista",
        "get_plantio_cultura",
        "get_plantio_variedade",
        "get_projeto_origem",
        "get_projeto_parcela",
        "get_nome_fantasia",
        "ticket",
        "op",
        "peso_bruto",
        "peso_tara",
        "get_peso_liquido",
        "umidade",
        "desconto_umidade",
        "impureza",
        "desconto_impureza",
        "peso_scs_limpo_e_seco",
        "bandinha",
        "desconto_bandinha",
        "peso_liquido",
        "peso_scs_liquido",
    )

    # raw_id_fields = ["plantio"]

    readonly_fields = (
        "peso_liquido",
        "peso_scs_limpo_e_seco",
        "peso_scs_liquido",
        "desconto_umidade",
        "desconto_impureza",
        "desconto_bandinha",
        "criados",
        "modificado",
    )

    search_fields = [
        "romaneio",
        "placa",
        "motorista",
        "deposito__nome_fantasia",
        "plantio__talhao__id_unico",
        "plantio__talhao__fazenda__nome",
        "plantio__talhao__fazenda__fazenda__nome",
        "plantio__variedade__variedade",
        "plantio__variedade__cultura__cultura",
    ]

    list_filter = (
        "plantio__safra__safra",
        "plantio__ciclo__ciclo",
        "deposito__nome",
        "plantio__talhao__fazenda__nome",
        "plantio__variedade__variedade",
    )

    ordering = ("-data_colheita",)

    def get_peso_liquido(self, obj):
        return obj.peso_bruto - obj.peso_tara

    get_peso_liquido.short_description = "Peso"

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
        if "Projeto" in obj.plantio.talhao.fazenda.nome:
            return obj.plantio.talhao.fazenda.nome.split("Projeto")[-1]
        else:
            return obj.plantio.talhao.fazenda.nome

    get_projeto_origem.short_description = "Origem"

    def get_plantio_cultura(self, obj):
        if obj.plantio.variedade is not None:
            cultura = (
                obj.plantio.variedade.cultura.cultura
                if obj.plantio.variedade.cultura.cultura
                else "-"
            )
            cultura_url = None
            if cultura == "Soja":
                cultura_url = "soy"
            if cultura == "Feijão":
                cultura_url = "beans2"
            if cultura == "Arroz":
                cultura_url = "rice"
            image_url = None
            if cultura_url is not None:
                image_url = f"/static/images/icons/{cultura_url}.png"
            if image_url is not None:
                return format_html(
                    f'<img style="width: 20px; height: 20px; text-align: center"  src="{image_url}">'
                )
        else:
            cultura = "Não Planejado"
        return cultura

    get_plantio_cultura.short_description = "Cultura"

    def get_plantio_variedade(self, obj):
        return obj.plantio.variedade.variedade

    get_plantio_variedade.short_description = "Variedade"

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
        "versao",
        "start_date_description",
        "end_date_description",
        "ativo",
    )

    search_fields = [
        "nome",
    ]

    list_filter = ("safra__safra", "ciclo__ciclo", "ativo")

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


def export_programa(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="Programas.csv"'
    response.write(codecs.BOM_UTF8)
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Programa",
            "Cultura",
            "Estagio",
            "Defensivo",
            "Tipo",
            "Dose",
            "Dap",
            "Safra",
            "Ciclo",
            "Ativo",
        ]
    )
    operacoes = (
        queryset.values_list(
            "operacao__programa__nome",
            "operacao__programa__cultura__cultura",
            "operacao__estagio",
            "defensivo__produto",
            "defensivo__tipo",
            "dose",
            "operacao__prazo_dap",
            "operacao__programa__safra__safra",
            "operacao__programa__ciclo__ciclo",
            "ativo",
        )
        .order_by("operacao__prazo_dap", "defensivo__tipo", "defensivo__produto")
        .filter(ativo=True)
        .filter(operacao__ativo=True)
    )
    for op in operacoes:
        op_details = list(op)
        op_details[5] = 0 if op[5] == None else str(op[5]).replace(".", ",")
        operation = tuple(op_details)
        writer.writerow(operation)
    return response


export_programa.short_description = "Export to csv"


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

    def save_model(self, request, obj, form, change):
        print(self)
        print(self.form)
        pass  # don't actually save the parent instance

    def save_formset(self, request, form, formset, change):
        form.instance.save()  # form.instance is the parent
        formset.save()  # this will save the children
        # print("Prazo antigo DAp: ", form.initial["prazo_dap"])
        # print("Novo Prazo", form.instance.prazo_dap)
        changed_dap = None
        if form.initial:
            changed_dap = form.initial["prazo_dap"] != form.instance.prazo_dap
        newDap = form.instance.prazo_dap
        if changed_dap == True:
            print("funcao pra alterar o prazo dap")
        if form.instance.ativo == True:
            query = Aplicacao.objects.select_related("operacao").filter(
                ativo=True, operacao=form.instance
            )
            produtos = [
                {
                    "dose": str(dose_produto.dose),
                    "tipo": dose_produto.defensivo.tipo,
                    "produto": dose_produto.defensivo.produto,
                    "quantidade aplicar": "",
                }
                for dose_produto in query
            ]
            current_op = form.instance.estagio
            current_program = form.instance.programa
            current_query = Plantio.objects.filter(
                programa=current_program, finalizado_plantio=True
            )
            admin_form_alter_programa_and_save(
                current_query, current_op, produtos, changed_dap, newDap
            )
        if form.instance.ativo == False:
            print("Estagio desativado: ", form.instance)
            current_op = form.instance.estagio
            current_program = form.instance.programa
            current_query = Plantio.objects.filter(
                programa=current_program, finalizado_plantio=True
            )
            admin_form_remove_index(current_query, current_op)

    list_display = (
        "estagio",
        "programa",
        "get_prazo_dap",
        "get_cultura_description",
        "get_obs_description",
        "ativo",
    )
    list_filter = [
        "programa",
        "programa__safra",
        "programa__ciclo",
        "modificado",
        "ativo",
    ]

    ordering = (
        "programa",
        "prazo_dap",
    )

    def get_cultura_description(self, obj):
        return obj.programa.cultura.cultura

    get_cultura_description.short_description = "Cultura"

    def get_prazo_dap(self, obj):
        return obj.prazo_dap

    get_prazo_dap.short_description = "DAP"

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
    actions = [export_programa]

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
        "operacao__programa",
        "operacao__programa__ciclo__ciclo",
        "operacao__programa__safra__safra",
        "ativo",
        "defensivo",
        "operacao",
        "defensivo__tipo",
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


@admin.register(AplicacaoPlantio)
class AplicacaoPlantioAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return (
            super(AplicacaoPlantioAdmin, self)
            .get_queryset(request)
            .select_related("plantio", "estagio", "defensivo", "estagio__programa")
        )

    list_display = (
        "estagio",
        "plantio",
        "defensivo",
        "dose",
        "data_prevista",
        "aplicado",
    )

    search_fields = (
        "estagio",
        "plantio",
        "defensivo",
        "dose",
        "data_prevista",
    )

    raw_id_fields = ["plantio"]


@admin.register(CicloAtual)
class SafraCicloAtual(admin.ModelAdmin):
    list_display = ("nome", "safra", "ciclo")


@admin.register(PlannerPlantio)
class PlannerPlantioAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return (
            super(PlannerPlantioAdmin, self)
            .get_queryset(request)
            .select_related(
                "projeto",
                "cultura",
                "ciclo",
                "cultura",
                "projeto__fazenda",
                "safra",
            )
        )

    list_display = (
        "projeto",
        "start_date_description",
        "cultura",
        "variedade",
        "safra_description",
        "area",
    )

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
