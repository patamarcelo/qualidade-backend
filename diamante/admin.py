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

from django.db.models import Q, Sum, F, Exists

from django.db.models import Subquery, OuterRef
from django.utils.formats import localize


from django.db.models import Case, When, DecimalField, Value
from django.db.models.functions import Coalesce, Round

from django.core import serializers
from django.contrib.admin import SimpleListFilter
from datetime import datetime, timedelta, date

from django.contrib import messages

from django.utils.html import escape


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

import requests

from admin_confirm.admin import AdminConfirmMixin, confirm_action
from django.urls import path
from django.http import HttpResponseRedirect

from usuario.models import CustomUsuario as User
from rest_framework.authtoken.models import Token


from qualidade_project.settings import DEBUG
from django.conf import settings
import dropbox

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from django.contrib.admin import DateFieldListFilter

from .forms import PlantioExtratoAreaForm


main_path = (
    "http://127.0.0.1:8000"
    if DEBUG == True
    else "https://diamante-quality.up.railway.app"
)


def get_cargas_model(safra_filter, ciclo_filter, list_ids=[]):
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
        .filter(plantio__safra__safra=safra_filter, plantio__ciclo__ciclo=ciclo_filter)
        .filter(~Q(plantio__id_farmbox__in=list_ids))
    ]
    return cargas_model




# class MyAdminSite(admin.AdminSite):
#     site_header = "teste para site header"
#     site_title = "teste para site title"
#     index_title = "Welcome to Admin index_title"
    
#     def get_urls(self):
#         urls = super().get_urls()
#         return urls
    
# admin_site = MyAdminSite(name="myadmin")

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
    safra_filter = None
    
    
    # ids parcelas J
    exclude_j = False
    # exclude_j = True
    if exclude_j:
        list_ids = [263066,264740]
    else:
        list_ids = []

    def get_queryset(self, request):
        global cicle_filter, safra_filter
        request.GET = request.GET.copy()
        ciclo = request.GET.pop("ciclo", None)
        safra = request.GET.pop("safra", None)
        print('ciclo: ', ciclo)
        print('safra: ', safra)
        if ciclo:
            ciclo_index = ciclo[0]
            safra_filter = safra[0].replace("_", "/").strip()
            cicle_filter = Ciclo.objects.filter(ciclo=ciclo_index)[0]
            safra_filter = Safra.objects.filter(safra=safra_filter)[0]
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
                .filter(ciclo=cicle_filter, safra=safra_filter)
                .order_by("data_plantio")
            )
        else:
            cicle_filter = CicloAtual.objects.filter(nome="Colheita")[0]
            cicle_filter = cicle_filter.ciclo
            safra_filter = CicloAtual.objects.filter(nome="Colheita")[0]
            safra_filter = safra_filter.safra
            print('retornando estes valores')
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
            # .filter(ciclo=cicle_filter, safra=safra_filter)
            .order_by("data_plantio")
        )

    def changelist_view(self, request, extra_context=None):
        
        
        request.GET = request.GET.copy()
        ciclo = request.GET.pop("ciclo", None)
        safra = request.GET.pop("safra", None)
        print('cicle here: ', ciclo)
        print('safra here: ', safra)
        
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        safra_ciclo = CicloAtual.objects.filter(nome="Colheita")[0]
        safra_filter = safra_ciclo.safra.safra
        cicle_filter = safra_ciclo.ciclo.ciclo
        
        print('self cicle filter', cicle_filter)
        if ciclo and safra:
            print('filter here: ')
            safra_filter = safra[0].replace('_', '/')
            cicle_filter = ciclo[0]
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
                ciclo__ciclo=cicle_filter,
                finalizado_plantio=True,
                plantio_descontinuado=False,
            )
            .filter(~Q(variedade__cultura__cultura="Milheto"))
            .filter(~Q(variedade__cultura__cultura="Algodão"))
            .filter(~Q(id_farmbox__in=self.list_ids))
            # .filter(~Q(talhao__fazenda__nome="Projeto Lago Verde"))
            .values(
                "talhao__fazenda__nome",
                "variedade__cultura__cultura",
                "variedade__variedade",
            )
            .annotate(**metrics)
            .order_by("talhao__fazenda__nome")
        )
        
        print(query_data)

        response.context_data["summary_2"] = json.dumps(
            list(query_data), cls=DjangoJSONEncoder
        )

        response.context_data["colheita_2"] = json.dumps(
            get_cargas_model(safra_filter, cicle_filter, self.list_ids), cls=DjangoJSONEncoder
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
    safra_filter = None

    def get_queryset(self, request):
        global cicle_filter, safra_filter
        request.GET = request.GET.copy()
        ciclo = request.GET.pop("ciclo", None)
        safra = request.GET.pop("safra", None)
        if ciclo:
            ciclo_index = ciclo[0]
            safra_filter = safra[0].replace("_", "/").strip()
            cicle_filter = Ciclo.objects.filter(ciclo=ciclo_index)[0]
            safra_filter = Safra.objects.filter(safra=safra_filter)[0]
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
                .filter(ciclo=cicle_filter, safra=safra_filter)
                .order_by("data_plantio")
            )
        else:
            cicle_filter = CicloAtual.objects.filter(nome="Plantio")[0]
            cicle_filter = cicle_filter.ciclo
            safra_filter = CicloAtual.objects.filter(nome="Plantio")[0]
            safra_filter = safra_filter.safra
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
            # .filter(ciclo=cicle_filter, safra=safra_filter)
            .order_by("data_plantio")
        )

    def changelist_view(self, request, extra_context=None):
        # global safra_filter
        request.GET = request.GET.copy()
        ciclo = request.GET.pop("ciclo", None)
        safra = request.GET.pop("safra", None)
        print('cicle here: ', ciclo)
        print('safra here: ', safra)
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        safra_ciclo = CicloAtual.objects.filter(nome="Plantio")[0]
        safra_filter = safra_ciclo.safra.safra
        cicle_filter = safra_ciclo.ciclo.ciclo
        
        print('self cicle filter', cicle_filter)
        if ciclo and safra:
            print('filter here: ')
            safra_filter = safra[0].replace('_', '/')
            cicle_filter = ciclo[0]
        # ciclo_filter = "1"
        # cicle_filter = Ciclo.objects.all()[0]
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        metrics = {
            "area_total": Sum("area_planejamento_plantio"),
            "area_plantada": Case(
                When(
                    Q(finalizado_plantio=True) | Q(inicializado_plantio=True),
                    then=Coalesce(Sum("area_colheita"), 0)),
                default=Value(0),
                output_field=DecimalField(),
            ),
            "area_projetada": Case(
                When(
                    Q(finalizado_plantio=False) | Q(inicializado_plantio=False),
                    then=Coalesce(Sum("area_planejamento_plantio"), 0)),
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
                ciclo__ciclo=cicle_filter,
                plantio_descontinuado=False,
                programa__isnull=False
            )
            .filter(~Q(variedade__cultura__cultura="Milheto"))
            .filter(~Q(variedade__cultura__cultura="Algodão"))
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


class EstagiosProgramaInline(admin.TabularInline):
    model = Operacao
    extra = 0
    fields = ["ativo", "estagio", "operacao_numero", "prazo_dap"]
    
    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)  # Add your custom CSS file here
        }


class AplicacoesProgramaInline(admin.TabularInline):
    model = Aplicacao
    extra = 0
    fields = ["defensivo", "dose", "ativo"]
    autocomplete_fields = ["defensivo"]
    
    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)  # Add your custom CSS file here
        }


@admin.register(Deposito)
class DepositoAdmin(admin.ModelAdmin):
    list_display = ("nome", "id_d")
    ordering = ("nome",)


@admin.register(Fazenda)
class FazendaAdmin(admin.ModelAdmin):
    list_display = ("nome", "id_d", "get_plantio_dia", "id_responsavel_farmbox","id_encarregado_farmbox")
    ordering = ("nome",) 
    show_full_result_count = False
    search_fields = ["fazenda"]

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
    list_display = ("cultura", "tipo_producao", 'id_protheus_planejamento')
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
        "id_farmbox"
    )
    ordering = ("variedade",)
    list_filter = [
        "cultura",
    ]
    search_fields = ["variedade", "id_farmbox"]


admin.site.register(Safra)
admin.site.register(Ciclo)


@admin.action(description="Exportar Plantio para Excel")
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
            "Plantio Descontinuado",
            "Area Planejada",
            "Data Prev Colheita",
            "area Plantada",
            "Data Plantio",
            # "Dap",
            "Ciclo Variedade",
            "Programa",
            "ID FarmBox",
            "Data Prevista Plantio",
            'Plantio Iniciado',
            "Cargas Carregadas",
            "Carregado Kg",
            "Produtividade",
            # "Area Parcial",
            # "Area a Considerar",
            "lat",
            "long",
            "dap",
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
        "plantio_descontinuado",
        "area_planejamento_plantio",
        "area_colheita",
        "data_plantio",
        "variedade__dias_ciclo",
        "programa__nome",
        "area_parcial",
        "map_centro_id",
        "id_farmbox",
        "data_prevista_plantio",
        "inicializado_plantio",
        "variedade__dias_germinacao",
    )
    cargas_list = modeladmin.total_c_2

    def get_total_prod(total_c_2, plantio):
        total_filt_list = sum([(x[1] * 60) for x in total_c_2 if plantio[0] == x[0]])
        prod_scs = 0
        if plantio[8]:
            try:
                prod = total_filt_list / plantio[11]
                prod_scs = prod / 60
            except ZeroDivisionError:
                prod_scs = float("Inf")
        if plantio[14]:
            try:
                if plantio[16] is not None:
                    print('total_filt', total_filt_list, 'plantio 16', plantio[16])
                    print('\n')
                    prod = total_filt_list / plantio[16]
                    prod_scs = prod / 60
            except ZeroDivisionError:
                prod_scs = float("Inf")
        if prod_scs:
            return localize(round(prod_scs, 2))
        else:
            return " - "

    def get_prev_colheita(data_plantio, timeDelta):
        if timeDelta != " - ":
            if data_plantio:
                prev_date_delta = timedelta(timeDelta)
                prev_date_final = data_plantio + prev_date_delta
                return prev_date_final
        else:
            return " - "

    def get_dap(data_plantio):
        dap = 0
        today = date.today()
        if data_plantio:
            dap = today - data_plantio
            dap = dap.days + 1
        return dap

    for plantio in plantios:
        plantio_detail = list(plantio)
        time_delta_variedade_germinacao = plantio_detail[-1]
        plantio_detail.pop()
        lat = ""
        lng = ""
        area_parcial = str(plantio_detail[15]).replace(".",",")
        area_plantada = str(plantio_detail[12]).replace(".",",") if plantio_detail[20] == True else ' - '
        if isinstance(plantio_detail[17], dict):
            lat = (
                str(plantio_detail[17]["lat"]).replace(".", ",")
                if plantio_detail[17]["lat"] != None
                else ""
            )
            lng = (
                str(plantio_detail[17]["lng"]).replace(".", ",")
                if plantio_detail[17]["lng"] != None
                else ""
            )
        plantio_detail.pop(17)
        data_plantio = plantio_detail[13] if plantio_detail[13] else plantio_detail[-2]
        time_delta_plantio = plantio_detail[14]
        plantio_detail[11] = localize(plantio_detail[11])
        cargas_carregadas_filter = [
            (x[1] * 60) for x in cargas_list if plantio_detail[0] == x[0]
        ]
        cargas_carregadas_kg = localize(sum(cargas_carregadas_filter))
        cargas_carregadas_quantidade = len(cargas_carregadas_filter)
        try:
            produtividade = get_total_prod(cargas_list, plantio)
        except:
            produtividade = 0
        plantio_detail.pop(16)
        plantio_detail.append(cargas_carregadas_quantidade)
        plantio_detail.append(cargas_carregadas_kg)
        plantio_detail.append(produtividade)
        # plantio_detail.append(str(area_parcial).replace(".", ','))
        # plantio_detail.append(area_considerar)
        plantio_detail.append(lat)
        plantio_detail.append(lng)
        plantio_detail.pop(0)
        time_delta_calc = time_delta_plantio + time_delta_variedade_germinacao if time_delta_plantio is not None and time_delta_variedade_germinacao is not None else " - "
        print('data plantio: ', data_plantio)
        print('time delta: ', time_delta_calc)
        plantio_detail.insert(11, get_prev_colheita(data_plantio, time_delta_calc))
        plantio_detail.append(get_dap(data_plantio))
        plantio_detail[12] = area_plantada
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


# class VariedadeInProgramaFilter(SimpleListFilter):
#     title = "Variedade in Programa"
#     parameter_name = "variedade_in_programa"

#     def lookups(self, request, model_admin):
#         return (
#             ("yes", "Sim"),
#             ("no", "Não"),
#         )

#     def queryset(self, request, queryset):
#         """
#         Filters the queryset based on the selected value.
#         """
#         queryset = queryset.select_related("variedade")
#         print('queryset', queryset)
        
#         if self.value() == "yes":
#             return queryset.filter(
#                 programa__variedade__pk__in=queryset.values_list("variedade__pk", flat=True)
#             ).distinct()
#         elif self.value() == "no":
#             return queryset.exclude(
#                 programa__variedade__pk__in=queryset.values_list("variedade__pk", flat=True)
#             ).distinct()
#         return queryset
class ColheitaFilterNoProgram(SimpleListFilter):
    title = "Sem Programa"  # or use _('country') for translated title
    parameter_name = "programas"

    def lookups(self, request, model_admin):
        return [
            ("com_programa", "Programa"),
            ("sem_programa", "Sem Programa"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "com_programa":
            return queryset.filter(~Q(programa_id=None))
        if self.value() == "sem_programa":
            return queryset.filter(Q(programa_id=None))


class ProgramaFilter(SimpleListFilter):
    title = "Programas"  # or use _('country') for translated title
    parameter_name = "programas"

    def lookups(self, request, model_admin):
        programas = Programa.objects.filter(ativo=True)
        return [(x.id, x.nome) for x in programas]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(programa_id=self.value()))
        return queryset


class ProgramaAplicacaoFilter(SimpleListFilter):
    title = "Programas"  # or use _('country') for translated title
    parameter_name = "programas"

    def lookups(self, request, model_admin):
        programas = Programa.objects.filter(ativo=True)
        return [(x.id, x.nome) for x in programas]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(operacao__programa_id=self.value()))
        return queryset


@admin.action(description="Aferição das Áreas")
def area_aferida(modeladdmin, request, queryset):
    count_true = 0
    ha_positivo = 0

    count_false = 0
    ha_negativo = 0
    for i in queryset:
        aferido = i.area_aferida
        if aferido == True:
            i.area_aferida = False
            count_false += 1
            ha_negativo += i.area_colheita
        else:
            i.area_aferida = True
            count_true += 1
            ha_positivo += i.area_colheita
        i.save()
    if count_true > 0:
        messages.add_message(
            request,
            messages.SUCCESS,
            f"{count_true} Áreas informadas como aferidas: {ha_positivo} hectares",
        )
    if count_false > 0:
        messages.add_message(
            request,
            messages.INFO,
            f"{count_false} Áreas informadas como NÃO aferidas: {ha_negativo} hectares",
        )


@admin.register(Plantio)
class PlantioAdmin(ExtraButtonsMixin, AdminConfirmMixin, admin.ModelAdmin):
    actions = [export_plantio, area_aferida]
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

    # @confirm_action
    @admin.action(description="Colher o Plantio")
    def finalize_plantio(self, request, queryset):
        queryset.update(finalizado_colheita=True)
        for obj in queryset:
            print("colheita finalizada")
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
                resp_code = response.status_code
                if int(resp_code) < 300:
                    print('resp obj: , ', resp_obj)
                    str_resp = f'Alterado no FARMBOX - {resp_obj["farm_name"]} - {resp_obj["name"]} - {resp_obj["harvest_name"]}-{resp_obj["cycle"]} - Produtividade: {resp_obj["productivity"]} - Variedade: {resp_obj["variety_name"]} - Area: {resp_obj["area"]}'
                    messages.add_message(request, messages.INFO, str_resp)
                if int(resp_code) > 400 and int(resp_code) < 500:
                    print('resp obj: , ', resp_obj)
                    str_resp = f'Erro ao Alterar no FarmBox - {response.status_code} - {response.text}'
                    messages.add_message(request, messages.ERROR, str_resp)
            except Exception as e:
                print("Erro ao alterar os dados no FarmBox")
                messages.add_message(
                    request,
                    messages.ERROR,
                    f"Erro ao salvar os dados no Farmbox: {e}",
                )

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
        print("dados atualizados com sucesso!!")
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
                "talhao__fazenda__fazenda",
                "variedade",
                "variedade__cultura",
                "programa"
            )
            .prefetch_related(
                "programa__variedade"
            )
        )

    def get_search_results(self, request, queryset, search_term):
        try:
            ciclo_filter = CicloAtual.objects.filter(nome="Colheita")[0]
        except IndexError:
            # Handle the case where CicloAtual doesn't exist
            # Return None or an empty queryset
            return None, False

        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )

        # Exclude only for autocomplete
        print("resquest_Path", request.path)
        model_request =  request.GET.get('model_name')
        print('model request: ', model_request)
        if model_request and model_request == 'plantioextratoarea':
            queryset = queryset.filter(
                ciclo__ciclo__in=["2", "3"],
                safra__safra="2024/2025",
                finalizado_colheita=False,
                plantio_descontinuado=False,
                programa__isnull=False,
            )
            if not queryset.exists():  # Check for empty queryset
                return None, False 
            return queryset, use_distinct

        if request.path == "/admin/autocomplete/":
            queryset = queryset.filter(
                ciclo=ciclo_filter.ciclo,
                finalizado_plantio=True,
                finalizado_colheita=False,
                plantio_descontinuado=False,
            )
            if not queryset.exists():  # Check for empty queryset
                return None, False 
            return queryset, use_distinct
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
        "programa__nome",
        "id_farmbox",
    ]
    raw_id_fields = ["talhao"]
    list_filter = (
        "safra__safra",
        "ciclo__ciclo",
        "variedade__cultura",
        ColheitaFilter,
        ColheitaFilterNoProgram,
        # VariedadeInProgramaFilter,
        "inicializado_plantio",
        "finalizado_plantio",
        "finalizado_colheita",
        "plantio_descontinuado",
        "talhao__fazenda__fazenda",
        "programa__nome",
        # "talhao__fazenda__nome",
        "variedade",
        "modificado",
        "area_aferida",
        # "area_parcial",
    )
    list_display = (
        "talhao",
        "cultura_description",
        "variedade_description",
        "safra_description",
        "programa",
        "get_data",
        "area_colheita",
        "get_dap_description",
        "get_data_prev_plantio",
        "get_description_inicializado_plantio",
        "get_description_finalizado_plantio",
        "get_data_prev_col",
        "get_description_finalizado_colheita",
        # "get_area_parcial",
        "get_total_colheita_cargas_kg",
        # "talhao",
        "get_total_prod",
        "get_data_primeira_carga",
        "get_data_ultima_carga",
        "get_total_colheita_cargas",
        "get_dias_ciclo",
        "get_description_descontinuado_plantio",
        "area_aferida",
        "area_parcial",
        # "check_var_on_programa_list"
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
                    ("area_planejamento_plantio"),
                    (
                        "area_colheita",
                        "area_parcial",
                    ),
                    ("safra", "ciclo"),
                    ("variedade", "programa"),
                    ("inicializado_plantio"),
                    ("finalizado_plantio", "finalizado_colheita"),
                    (
                        "data_plantio",
                        "data_emergencia",
                    ),
                    ("data_prevista_colheita", "data_prevista_plantio"),
                    ("area_aferida",),
                    ("plantio_descontinuado",),
                    ("farmbox_update",),
                    ("observacao",),
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
                    resp_code = response.status_code
                    if int(resp_code) < 300:
                        print('resp obj: , ', resp_obj)
                        str_resp = f'Alterado no FARMBOX - {resp_obj["farm_name"]} - {resp_obj["name"]} - {resp_obj["harvest_name"]}-{resp_obj["cycle"]} - Produtividade: {resp_obj["productivity"]} - Variedade: {resp_obj["variety_name"]} - Area: {resp_obj["area"]}'
                        messages.add_message(request, messages.INFO, str_resp)
                    if int(resp_code) > 400 and int(resp_code) < 500:
                        print('resp obj: , ', resp_obj)
                        str_resp = f'Erro ao Alterar no FarmBox - {response.status_code} - {response.text}'
                        messages.add_message(request, messages.ERROR, str_resp)
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
        peso_total = sum(filtered_list) if sum(filtered_list) > 0 else " - "
        return peso_total

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
        if obj.area_parcial != None and obj.area_parcial > 0 and total_filt_list == 0:
            return 0
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

    def get_description_inicializado_plantio(self, obj):
        return obj.inicializado_plantio

    get_description_inicializado_plantio.boolean = True
    get_description_inicializado_plantio.short_description = "Start Plantio"
    
    def get_description_finalizado_plantio(self, obj):
        return obj.finalizado_plantio

    get_description_finalizado_plantio.boolean = True
    get_description_finalizado_plantio.short_description = "End Plantio"

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
        if obj.data_plantio and obj.variedade:
            prev_date_delta = timedelta(
                obj.variedade.dias_ciclo + obj.variedade.dias_germinacao
            )
            prev_date_final = obj.data_plantio + prev_date_delta
            return date_format(
                prev_date_final, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data_prev_col.short_description = "Data Prev. Col."
    
    def get_data_prev_plantio(self, obj):
        if obj.data_prevista_plantio and obj.variedade:
            return date_format(
                obj.data_prevista_plantio, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data_prev_plantio.short_description = "Data Prev. Plantio"

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
    
    def check_var_on_programa_list(self,obj):
        if obj.programa and obj.variedade:
                
            ins_in_programa =  obj.programa.variedade.filter(pk=obj.variedade.pk).exists()
            return ins_in_programa
    
    check_var_on_programa_list.boolean = True  # Display as a boolean field
    check_var_on_programa_list.short_description = "Variedade / Programa"
        

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


class SomeModelForm(forms.Form):
    csv_file = forms.FileField(required=False, label="please select a file")


@admin.register(Colheita)
class ColheitaAdmin(admin.ModelAdmin):
    autocomplete_fields = ["plantio"]
    change_list_template = "admin/change_list_colheita.html"

    def get_urls(self):
        urls = super().get_urls()
        # my_urls = [path(r"^upload_csv/$", self.upload_csv, name="upload_csv")]
        my_urls = [path("upload_csv/", self.upload_csv, name="upload_csv")]

        return my_urls + urls

    urls = property(get_urls)

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
                    ("ativo", "id_farmtruck"),
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
                    ("get_peso_liquido", 'peso_scs_liquido'),
                    ("peso_liquido", "peso_scs_limpo_e_seco"),
                )
            },
        ),
        (
            "Descontos",
            {
                "fields": (
                    ("umidade", "desconto_umidade"),
                    ("impureza", "desconto_impureza"),
                    # ("bandinha", "desconto_bandinha"),
                )
            },
        ),
        ("Observações", {"fields": (("observacao",))}),
    )

    list_display = (
        "romaneio",
        "get_data_colheita",
        "get_placa",
        # "get_nome_motorista",
        "get_plantio_cultura",
        "get_plantio_variedade",
        "get_projeto_origem",
        "get_projeto_parcela",
        "get_nome_fantasia",
        "ticket",
        "peso_bruto",
        "peso_tara",
        "get_peso_liquido",
        "umidade",
        "desconto_umidade",
        "impureza",
        "desconto_impureza",
        # "peso_scs_limpo_e_seco",
        # "bandinha",
        # "desconto_bandinha",
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
        "id_farmtruck",
        "get_peso_liquido"
    )

    search_fields = [
        "romaneio",
        "placa",
        "ticket",
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

    ordering = ("-data_colheita", "-romaneio")

    def upload_csv(self, request):
        if request.method == "POST":
            user_id = Token.objects.get(user=request.user)
            form = SomeModelForm(request.POST, request.FILES)
            if form.is_valid():
                data_file = request.FILES["csv_file"]
                data_json = json.load(data_file)

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Token {user_id}",
                }
                response = requests.post(
                    f"{main_path}/diamante/colheita/save_from_protheus/",
                    headers=headers,
                    json=data_json,
                )
                resp = json.loads(response.text)
                includes = resp["data"]["includes"]
                not_includes = resp["data"]["notincludes"]
                failed_loads = resp["failed_load"]
                success_loads = resp["success_load"]
                if includes > 0:
                    msg = f"{includes} Cargas incuídas com Sucesso"
                    messages.add_message(request, messages.SUCCESS, msg)
                    success_format = list(
                        map(
                            lambda x: f"{x['romaneio']} - Ticket: {x['ticket']} - {x['projeto']}: {x['parcela']}",
                            success_loads,
                        )
                    )
                    for success in success_format:
                        messages.add_message(
                            request, messages.SUCCESS, mark_safe(success)
                        )
                if not_includes > 0:
                    msg = f"{not_includes} Cargas não incluídas"
                    failed_format = list(
                        map(
                            lambda x: f"Romaneio: {x['romaneio']} - {x['projeto']}: {x['parcela']} <br/> {x['error']}",
                            failed_loads,
                        )
                    )
                    messages.add_message(request, messages.WARNING, msg)
                    for failed in failed_format:
                        messages.add_message(request, messages.ERROR, mark_safe(failed))

        return HttpResponseRedirectToReferrer(request)

    # def changelist_view(self, *args, **kwargs):
    #     view = super().changelist_view(*args, **kwargs)
    #     print(self)
    #     # view.context_data["submit_csv_form"] = SomeModelForm
    #     return view

    def get_peso_liquido(self, obj):
        if obj.peso_bruto is not None and obj.peso_tara is not None:
            return obj.peso_bruto - obj.peso_tara
        else:
            return " - "

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
    readonly_fields = ["modificado"]
    filter_horizontal = ('variedade',)  # Field name

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

    fieldsets = [
        (
            "Dados",
            {
                "fields": (
                    ("ativo", "modificado"),
                    ("nome", "nome_fantasia"),
                    ("safra", "ciclo"),
                    ("cultura"),
                    ("programa_por_data", "programa_por_estagio"),
                    ("start_date", "end_date"),
                    ("variedade"),
                    ("versao"),
                )
            },
        )
    ]

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
            "Unidade Medida",
            "id Farmbox",
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
            "defensivo__unidade_medida",
            "defensivo__id_farmbox",
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
            .filter(programa__ativo=True)
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
        
        # Alterando o nome do estagio do programa
        nome_estagio_alterado = False
        estagio_alterado = 'Novo Nome'
        if form.initial:
            estagio_original = form.instance.estagio.strip()
            estagio_alterado = form.initial['estagio'].strip()
            print('nome alterado:', estagio_original)
            print('nome original: ', estagio_alterado)
            print('estagios sao diferentes: ', estagio_original != estagio_alterado) 
            if estagio_original != estagio_alterado:
                nome_estagio_alterado = True
                
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
                    "id_farmbox": dose_produto.defensivo.id_farmbox,
                    "formulacao": dose_produto.defensivo.unidade_medida,
                    "quantidade aplicar": "",
                }
                for dose_produto in query
            ]
            if nome_estagio_alterado == True:
                current_op = form.initial['estagio']
                estagio_alterado = form.instance.estagio
            else:
                current_op = form.instance.estagio
            current_program = form.instance.programa
            current_query = Plantio.objects.filter(
                programa=current_program, finalizado_plantio=True
            )
            admin_form_alter_programa_and_save(
                current_query, current_op, produtos, changed_dap, newDap, nome_estagio_alterado, estagio_alterado
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
        ProgramaFilter,
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
        if obj.observacao or obj.obs:
            return f"{obj.obs[:20] }..."
        else:
            return " - "

    get_obs_description.short_description = "Obs"


@admin.register(Defensivo)
class DefensivoAdmin(admin.ModelAdmin):
    list_display = ("produto", "tipo", 'id_farmbox', 'unidade_medida')
    # ordering = ["operacao__estagio", "produto"]
    ordering = ["produto"]
    search_fields = ["produto", "tipo", 'id_farmbox']
    list_filter = ("tipo",)
    show_full_result_count = False


@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    actions = [export_programa]

    def get_queryset(self, request):
        return (
            super(AplicacaoAdmin, self)
            .get_queryset(request)
            .filter(operacao__programa__ativo=True, operacao__ativo=True)
            .select_related("operacao", "defensivo", "operacao__programa")
        )

    show_full_result_count = False

    list_display = (
        "operacao",
        "programa",
        "defensivo",
        "defensivo__formulacao",
        "defensivo__unidade_medida",
        "defensivo__id_farmbox",
        "dose",
        "get_operacao_prazo_dap",
        "related_link",
        "ativo",
    )
    search_fields = [
        "operacao__programa__nome",
        "operacao__estagio",
        "defensivo__produto",
        "defensivo__tipo",
        "dose",
    ]
    raw_id_fields = ["operacao"]
    list_filter = (
        ProgramaAplicacaoFilter,
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
    
    def related_link(self, obj):
            if obj.operacao:
                url = reverse('admin:diamante_operacao_change', args=[obj.operacao.id])
                return format_html('<a href="{}">{}</a>', url, obj.operacao)
            return "-"
    related_link.short_description = "Estágio"

    
    def defensivo__id_farmbox(self, obj):
        return obj.defensivo.id_farmbox

    defensivo__id_farmbox.short_description = "id Farm"
    
    def defensivo__unidade_medida(self, obj):
        return obj.defensivo.get_unidade_medida_display()

    defensivo__unidade_medida.short_description = "Unidade"
    
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


class RegistroVisitasAdminInline(admin.TabularInline):
    model = RegistroVisitas
    extra = 0
    fields = ["ativo", "image", "image_title", "obs"]

    def get_queryset(self, request):
        print("getttt")
        return (
            super(RegistroVisitasAdminInline, self)
            .get_queryset(request)
            .select_related("visita__fazenda", "visita")
            .prefetch_related("visita__projeto", "visita__projeto__fazenda")
        )


@admin.register(Visitas)
class VisitasAdmin(admin.ModelAdmin):
    show_full_result_count = False
    autocomplete_fields = ["fazenda", "projeto"]
    inlines = [RegistroVisitasAdminInline]

    def get_queryset(self, request):
        print(self, request, "tryng overide here")
        return (
            super(VisitasAdmin, self)
            .get_queryset(request)
            .select_related("fazenda")
            .prefetch_related("projeto")
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
            "Visita",
            {
                "fields": (
                    ("data",),
                    ("fazenda",),
                    ("projeto",),
                    ("resp_visita",),
                    ("resp_fazenda"),
                    ("observacoes_gerais"),
                )
            },
        ),
    )
    readonly_fields = (
        "criados",
        "modificado",
    )

    list_display = (
        "get_fazenda_name",
        "data",
        "resp_visita",
        "resp_fazenda",
        "observacoes_gerais",
    )
    filter_horizontal = ("projeto",)

    def get_fazenda_name(self, obj):
        return obj.fazenda.nome

    get_fazenda_name.short_description = "Fazenda"

    # ordering = ["produto"]
    # search_fields = ["produto", "tipo"]
    # list_filter = ("tipo",)
    # show_full_result_count = False
    # def save_model(self, request, obj, form, change):
    #     print(self)
    #     print(self.form)
    #     pass  # don't actually save the parent instance

    # def save_formset(self, request, form, formset, change):
    #     print("arquivos")
    #     print(self)
    #     dbx = dropbox.Dropbox(
    #         app_key=settings.DROPBOX_APP_KEY,
    #         app_secret=settings.DROPBOX_APP_SECRET,
    #         oauth2_refresh_token=settings.DROPBOX_OAUTH2_REFRESH_TOKEN,
    #         timeout=100,
    #     )
    #     images = request.FILES
    #     for i in images.items():
    #         file_name = FileSystemStorage(location="/tmp").save(i[1].name, i[1])
    #         file_url = os.path.join("/", file_name)
    #         file_link_metadata = dbx.sharing_create_shared_link_with_settings(file_url)
    #         downloadable_url = file_link_metadata.url.replace("dl=0", "dl=1")
    #         print(downloadable_url)


@admin.register(RegistroVisitas)
class RegistroVisitasAdmin(admin.ModelAdmin):
    show_full_result_count = False

    def get_queryset(self, request):
        print(self, request, "tryng overide")
        return (
            super(RegistroVisitasAdmin, self)
            .get_queryset(request)
            .select_related("visita", "visita__fazenda")
        )

    list_display = ("get_fazenda_name", "get_date_of", "image_title", "image_tag")
    # ordering = ["produto"]
    # search_fields = ["produto", "tipo"]
    # list_filter = ("tipo",)
    # show_full_result_count = False
    readonly_fields = ("image_tag",)

    def get_date_of(self, obj):
        return obj.visita.data

    get_date_of.short_description = "Data"

    def get_fazenda_name(self, obj):
        return obj.visita.fazenda.nome

    get_fazenda_name.short_description = "Fazenda"

    def image_tag(self, obj):
        return format_html(
            '<img src="{}" style="max-width:50px; max-height:50px"/>'.format(
                obj.image.url
            )
        )

    image_tag.short_description = "Foto"
    image_tag.allow_tags = True



@admin.register(AppFarmboxIntegration)
class AppFarmBoxIntegrationAdmin(admin.ModelAdmin):
    
    list_display = ("get_data", "app_nuumero", "app_fazenda")
    search_fields=("app_nuumero","criados",'app_fazenda')

    def get_data(self, obj):
        if obj.criados:
            return date_format(
                obj.criados, format="SHORT_DATETIME_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data.short_description = "Data Abertura"
    
    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="50vh", mode="tree")
        },
    }

@admin.register(StProtheusIntegration)
class StProtheusIntegrationAdmin(admin.ModelAdmin):
    
    list_display = ("get_data", "st_numero", "st_fazenda")
    list_filter = (
        ("criados", DateFieldListFilter),  # Filters by the 'criados' date field
    )
    readonly_fields = ("criados","modificado")
    
    formfield_overrides = {
        models.JSONField: {
            "widget": JSONEditorWidget(width="200%", height="75vh", mode="tree")
        },
    }
    fieldsets = (
        (
            "Dados",
            {
                "fields": (
                    ("criados"),
                    ("ativo"),
                    ("st_numero",),
                    ("st_fazenda",),
                    ("app",),
                )
            },
        ),
    )
    
    
    def get_data(self, obj):
        if obj.criados:
            return date_format(
                obj.criados, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data.short_description = "Data Abertura"
    

@admin.action(description="Exportar Plantio para Excel")
def export_plantio_extrato(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="ExtratoPlantio.csv"'
    response.write(codecs.BOM_UTF8)
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "data",
        "Parcela",
        'Projeto',
        'Safra',
        'Ciclo',
        'Cultura',
        'Variedade',
        'Area',
        'Ativo'
    ])
    
    plantios = queryset.select_related('plantio', 'plantio__safra', 'plantio__ciclo').values_list(
        'data_plantio',
        'plantio__talhao__id_talhao',
        'plantio__talhao__fazenda__nome',
        'plantio__safra__safra',
        "plantio__ciclo__ciclo",
        'plantio__variedade__cultura__cultura',
        "plantio__variedade__variedade",
        "area_plantada",
        'ativo'
    )
    
    for plantio in plantios:
        plantio_detail = list(plantio)
        plantio_detail[-2] = str(plantio_detail[-2]).replace('.', ',')
        plantio = tuple(plantio_detail)
        writer.writerow(plantio)
    return response
@admin.register(PlantioExtratoArea)
class PlantioExtratoAreaAdmin(admin.ModelAdmin):
    form = PlantioExtratoAreaForm
    actions =[export_plantio_extrato]
    
    
    list_display = ("talhao_description", "get_data", "safra_description", "cultura_description", "variedade_description", "area_plantada","related_link", 'ativo')
    autocomplete_fields = ["plantio"]
    raw_id_fields = ["plantio"]
    readonly_fields = ("criados","modificado")
    ordering = ["-data_plantio"]
    list_filter = ['aguardando_chuva', 'ativo','plantio__safra__safra', 'plantio__ciclo__ciclo', 'plantio__variedade__cultura']
    search_fields = [
        "plantio__variedade__variedade", 
        "plantio__variedade__cultura__cultura",
        "plantio__talhao__fazenda__nome",
        "plantio__talhao__fazenda__fazenda__nome",
        "plantio__talhao__id_unico",
        "data_plantio"
        ]
    
    def get_queryset(self, request):
        return (
            super(PlantioExtratoAreaAdmin, self)
            .get_queryset(request)
            .select_related(
                "plantio__talhao",
                "plantio__safra",
                "plantio__ciclo",
                "plantio__talhao__fazenda",
                "plantio__variedade",
                "plantio__variedade__cultura",
            )
        )
    
    fieldsets = (
        (
            "Dados",
            {
                "fields": (
                    ("ativo"),
                    ("criados", 'modificado'),
                )
            },
        ),
        (
            "Plantio",
            {
                'fields': (
                    ("plantio",),
                    ("data_plantio"),
                    ("area_plantada"),
                    # ("aguardando_chuva",),
                    ("finalizado_plantio",)
                )
            }
        ),
    )
    
    def talhao_description(self, obj):
        return obj.plantio.talhao
    talhao_description.short_description = 'Talhão'
    
    def related_link(self, obj):
        if obj.plantio:
            url = reverse('admin:diamante_plantio_change', args=[obj.plantio.id])
            return format_html('<a href="{}">{}</a>', url, obj.plantio)
        return "-"
    related_link.short_description = "Plantio"

    
    def get_data(self, obj):
        if obj.data_plantio:
            return date_format(
                obj.data_plantio, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data.short_description = "Data Plantio"
    
    
    def safra_description(self, obj):
        return f"{obj.plantio.safra.safra} - {obj.plantio.ciclo.ciclo}"

    safra_description.short_description = "Safra"
    
    def cultura_description(self, obj):
        if obj.plantio.variedade is not None:
            cultura = (
                obj.plantio.variedade.cultura.cultura if obj.plantio.variedade.cultura.cultura else "-"
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
    
    def variedade_description(self, obj):
        if obj.plantio.variedade:
            variedade = (
                obj.plantio.variedade.nome_fantasia if obj.plantio.variedade.nome_fantasia else "-"
            )
        else:
            variedade = "Não Planejado"
        return variedade

    variedade_description.short_description = "Variedade"
    
    class Media:
        css = {
            'all': ('admin/css/custom.css',)  # Path to your custom CSS
        }
    

@admin.register(ColheitaPlantioExtratoArea)
class ColheitaPlantioExtratoAreaAdmin(admin.ModelAdmin):
    list_display = ("talhao_description", "safra_description", "cultura_description", "variedade_description", "get_data", "area_colhida")
    autocomplete_fields = ["plantio"]
    raw_id_fields = ["plantio"]
    ordering = ["-data_colheita"]
    list_filter = ["plantio__safra", "plantio__ciclo"]
    search_fields = [
        "plantio__variedade__variedade", 
        "plantio__variedade__cultura__cultura",
        "plantio__talhao__fazenda__nome",
        "plantio__talhao__fazenda__fazenda__nome",
        "plantio__talhao__id_unico"
        ]
    
    def get_queryset(self, request):
        return (
            super(ColheitaPlantioExtratoAreaAdmin, self)
            .get_queryset(request)
            .select_related(
                "plantio__talhao",
                "plantio__safra",
                "plantio__ciclo",
                "plantio__talhao__fazenda",
                "plantio__variedade",
                "plantio__variedade__cultura",
            )
        )
    
    def get_data(self, obj):
        if obj.data_colheita:
            return date_format(
                obj.data_colheita, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "

    get_data.short_description = "Data Colheita"
    
    
    def safra_description(self, obj):
        return f"{obj.plantio.safra.safra} - {obj.plantio.ciclo.ciclo}"

    safra_description.short_description = "Safra"
    
    
    def talhao_description(self, obj):
        return obj.plantio.talhao
    talhao_description.short_description = 'Talhão'
    
    def cultura_description(self, obj):
        if obj.plantio.variedade is not None:
            cultura = (
                obj.plantio.variedade.cultura.cultura if obj.plantio.variedade.cultura.cultura else "-"
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
    
    def variedade_description(self, obj):
        if obj.plantio.variedade:
            variedade = (
                obj.plantio.variedade.nome_fantasia if obj.plantio.variedade.nome_fantasia else "-"
            )
        else:
            variedade = "Não Planejado"
        return variedade

    variedade_description.short_description = "Variedade"
    
    
@admin.register(HeaderPlanejamentoAgricola)
class HeaderPlanejamentoAgricolaAdmin(admin.ModelAdmin):
    list_display = ("criados", "projeto", "codigo_planejamento", "safra", "ciclo")

@admin.register(BuyProducts)
class BuyProductsAdmin(admin.ModelAdmin):
    filter_horizontal = ('projeto',) 
    autocomplete_fields = ["defensivo"]
    list_display = ("defensivo", "get_fazenda_name", 'quantidade_comprada','sit_pago', 'get_data_pgto', 'fornecedor', 'nota_fiscal')
    search_fields = ["defensivo__produto", 'fazenda__nome', 'quantidade_comprada','sit_pago', 'data_pagamento', 'fornecedor', 'nota_fiscal']
    list_filter = ["fazenda",'sit_pago']
    
    
    def get_fazenda_name(self, obj):
        return obj.fazenda.nome

    get_fazenda_name.short_description = "Fazenda"
    
    
    def get_data_pgto(self, obj):
        if obj.data_pagamento:
            return date_format(
                obj.data_pagamento, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "
    get_data_pgto.short_description = "Data Pgto"
    
    def changelist_view(self, request, extra_context=None):
        queryset = BuyProducts.objects.all()

        # Aggregate by defensivo and then by fazenda
        aggregated_data = {}

        # Group by defensivo
        defensivo_totals = queryset.values('defensivo__produto').annotate(
            total_defensivo=Sum('quantidade_comprada')
        )

        for defensivo in defensivo_totals:
            defensivo_name = defensivo['defensivo__produto']
            total_defensivo = defensivo['total_defensivo']

            # For each defensivo, get the subtotals by fazenda
            fazenda_totals = queryset.filter(defensivo__produto=defensivo_name).values('fazenda__nome').annotate(
                total_fazenda=Sum('quantidade_comprada')
            )

            aggregated_data[defensivo_name] = {
                'total_defensivo': total_defensivo,
                'fazendas': fazenda_totals
            }

        extra_context = extra_context or {}
        extra_context['aggregated_data'] = aggregated_data

        return super().changelist_view(request, extra_context=extra_context)
    
    readonly_fields = ("criados","modificado")
    fieldsets = (
        (
            "Dados",
            {
                "fields": (
                    ("ativo"),
                    ("criados", "modificado"),
                )
            },
        ),
        (
            "Produto",
            {
                "fields": (
                    ("defensivo", "quantidade_comprada"),
                    ("fazenda"),
                    # ("projeto"),
                    ("sit_pago", 'data_pagamento'),
                    ('fornecedor','nota_fiscal'),
                    ('nr_pedido'),
                )
            },
        ),
        (
            "Arquivo",
            {
                "fields": (
                    ("nf_file"),
                )
            },
        ),
        ("Observações", {"fields": (("observacao",))}),
    )

def format_number_nf(number_str):
    if not number_str:
        return ' - '
    # Reverse the string to process it from the end
    reversed_str = str(number_str)[::-1]
    
    # Group digits in chunks of 3 and join them with a dot
    grouped = ".".join(reversed_str[i:i+3] for i in range(0, len(reversed_str), 3))
    
    # Reverse the result back to the original order
    formatted_number = grouped[::-1]
    
    return formatted_number
@admin.register(SentSeeds)
class SentSeedsAdmin(admin.ModelAdmin):
    readonly_fields = ("peso_total","criados", "modificado")
    autocomplete_fields = ["variedade",'origem']
    raw_id_fields = ["variedade"]
    list_display = [
        "get_data_envio", "origem", 'get_destino_name',"safra_description", 'cultura_description' , 'variedade', "get_quantidade_bags","get_peso_bag",  'get_peso_enviado', 'get_nf'
    ]
    search_fields = [
        "data_envio", "origem__nome", 'destino__nome', 'variedade__variedade', 'peso_total', 'nota_fiscal'
    ]
    list_filter = ['destino', 'variedade']
    
    fieldsets = (
        (
            "Dados",
            {
                "fields": (
                    ("ativo"),
                    ("criados", "modificado"),
                )
            },
        ),
        (
            "Envio Da semente",
            {
                "fields": (
                    ("data_envio", "variedade"),
                    ("quantidade_bags", 'peso_bag'),
                    ("peso_total"),
                    ("nota_fiscal"),
                    ("origem", 'destino'),
                    ('safra', 'ciclo'),
                    # ("observacao",)
                    
                )
            },
        ),
        # ("Observações", {"fields": (("observacao",))}),
    )

    
    
    def get_peso_bag(self, obj):
        return obj.peso_bag
    get_peso_bag.short_description = "Peso Bag"
    
    def get_nf(self, obj):
        return format_number_nf(obj.nota_fiscal)
    get_nf.short_description = "Nº NF"
    
    def get_peso_enviado(self, obj):
        return obj.peso_total
    get_peso_enviado.short_description = "Peso Enviado / Kg"
    
    def get_quantidade_bags(self, obj):
        return obj.quantidade_bags
    get_quantidade_bags.short_description = "Bags"
    
    def get_destino_name(self, obj):
        return obj.destino.nome.replace('Fazenda ', '')
    get_destino_name.short_description = "Destino"
    
    def get_queryset(self, request):
        return (
            super(SentSeedsAdmin, self)
            .get_queryset(request)
            .select_related(
                "safra",
                "ciclo",
                "origem",
                "destino",
                "variedade",
                "variedade__cultura",
            )
        )
    
    def get_data_envio(self, obj):
        if obj.data_envio:
            return date_format(
                obj.data_envio, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "
    get_data_envio.short_description = "Data Pgto"
    
    def safra_description(self, obj):
        return f"{obj.safra.safra} - {obj.ciclo.ciclo}"

    safra_description.short_description = "Safra"
    
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

@admin.register(SeedStock)
class SeedStockAdmin(admin.ModelAdmin):
    list_display = ["get_data_envio", 'fazenda', "cultura_description", 'variedade', 'estoque_atual']
    
    def get_queryset(self, request):
        return (
            super(SeedStockAdmin, self)
            .get_queryset(request)
            .select_related(
                "fazenda",
                "variedade",
                "variedade__cultura",
            )
        )
    def get_data_envio(self, obj):
        if obj.data_apontamento:
            return date_format(
                obj.data_apontamento, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "
    get_data_envio.short_description = "Data Envio"
    
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
    

@admin.register(SeedConfig)
class SeedConfigAdmin(admin.ModelAdmin):
    list_display = ["get_data_envio", 'fazenda', "variedade", 'variedade', 'regulagem']
    
    def get_queryset(self, request):
        return (
            super(SeedConfigAdmin, self)
            .get_queryset(request)
            .select_related(
                "fazenda",
                "variedade",
                "variedade__cultura",
            )
        )
    def get_data_envio(self, obj):
        if obj.data_apontamento:
            return date_format(
                obj.data_apontamento, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "
    get_data_envio.short_description = "Data Envio"
    
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