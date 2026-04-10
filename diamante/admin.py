from __future__ import annotations

import codecs
import csv
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal, DivisionByZero, InvalidOperation
from threading import Thread
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import dropbox
import requests
from admin_confirm.admin import AdminConfirmMixin, confirm_action
from admin_extra_buttons.api import (
    ExtraButtonsMixin,
    button,
    confirm_action,
    link,
    view,
)
from admin_extra_buttons.utils import HttpResponseRedirectToReferrer
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.contrib.admin import SimpleListFilter, helpers
from django.contrib.admin.helpers import ActionForm as AdminActionForm
from django.core import serializers
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.db import connection, transaction, close_old_connections
from django.db.models import (
    Q,
    Sum,
    F,
    Exists,
    CharField,
    Subquery,
    OuterRef,
    Case,
    When,
    DecimalField,
    Value,
    IntegerField,
)
from django.db.models.functions import Coalesce, Round
from django.db.models.query import QuerySet
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.http.request import HttpRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.formats import date_format, localize
from django.utils.html import escape, format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.timezone import is_naive, make_aware
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.detail import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django_json_widget.widgets import JSONEditorWidget
from rest_framework.authtoken.models import Token

from qualidade_project.settings import DEBUG
from usuario.models import CustomUsuario as User

from .forms import (
    AplicacoesProgramaInlineFormSet,
    BulkReplaceAplicacaoForm,
    PlantioExtratoAreaForm,
    ProgramaAdminForm,
    UpdateDataPrevistaPlantioForm,
)
from .models import *
from .services.generate_kml import create_kml
from .utils import (
    admin_form_alter_programa_and_save,
    admin_form_remove_index,
    close_plantation_and_productivity,
    duplicate_existing_operations_program_and_applications,
    processar_programa_em_background,
    update_farmbox_data,
)
from .views_api import save_from_protheus_logic

logger = logging.getLogger(__name__)

def parse_date_start(date_str):
    if not date_str:
        return None
    parsed = parse_date(date_str)
    if not parsed:
        return None
    dt = datetime.combine(parsed, dt_time.min)
    return make_aware(dt) if is_naive(dt) else dt


def parse_date_end(date_str):
    if not date_str:
        return None
    parsed = parse_date(date_str)
    if not parsed:
        return None
    dt = datetime.combine(parsed, dt_time.max)
    return make_aware(dt) if is_naive(dt) else dt

def build_created_filters(created_at_gte=None, created_at_lte=None, field_name="criados"):
    filters = Q()
    dt_gte = parse_date_start(created_at_gte)
    dt_lte = parse_date_end(created_at_lte)

    if dt_gte:
        filters &= Q(**{f"{field_name}__gte": dt_gte})
    if dt_lte:
        filters &= Q(**{f"{field_name}__lte": dt_lte})

    return filters


def build_date_filters(data_gte=None, data_lte=None, field_name="data_colheita"):
    filters = Q()

    if data_gte:
        filters &= Q(**{f"{field_name}__gte": data_gte})
    if data_lte:
        filters &= Q(**{f"{field_name}__lte": data_lte})

    return filters



main_path = (
    "http://127.0.0.1:8000"
    if DEBUG == True
    else "https://diamante-quality.up.railway.app"
)


def get_cargas_model(
    safra_filter,
    ciclo_filter,
    list_ids=None,
    created_at_gte=None,
    created_at_lte=None,
    data_gte=None,
    data_lte=None,
):
    list_ids = list_ids or []

    created_filters = build_created_filters(
        created_at_gte=created_at_gte,
        created_at_lte=created_at_lte,
        field_name="criados",
    )

    data_filters = build_date_filters(
        data_gte=data_gte,
        data_lte=data_lte,
        field_name="data_colheita",
    )

    cargas_qs = (
        Colheita.objects.values(
            "plantio__talhao__fazenda__nome",
            "plantio__variedade__cultura__cultura",
            "plantio__variedade__variedade",
        )
        .annotate(
            peso_kg=Sum(F("peso_liquido") * 60),
            peso_scs=Round(Sum("peso_scs_limpo_e_seco"), precision=2),
        )
        .order_by("plantio__talhao__fazenda__nome")
        .filter(~Q(plantio__variedade__cultura__cultura="Milheto"))
        .filter(
            plantio__safra__safra=safra_filter,
            plantio__ciclo__ciclo=ciclo_filter,
        )
        .filter(~Q(plantio__id_farmbox__in=list_ids))
        .filter(plantio__acompanhamento_medias=True)
    )

    if created_at_gte or created_at_lte:
        cargas_qs = cargas_qs.filter(created_filters)

    if data_gte or data_lte:
        cargas_qs = cargas_qs.filter(data_filters)

    return [x for x in cargas_qs]




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

    cicle_filter = None
    safra_filter = None

    exclude_j = False
    if exclude_j:
        list_ids = [263066, 264740]
    else:
        list_ids = []

    def get_queryset(self, request):
        global cicle_filter, safra_filter

        request.GET = request.GET.copy()

        ciclo = request.GET.pop("ciclo", None)
        safra = request.GET.pop("safra", None)

        # remove também os filtros customizados para o admin não tentar processar
        request.GET.pop("created_at_gte", None)
        request.GET.pop("created_at_lte", None)
        request.GET.pop("data_gte", None)
        request.GET.pop("data_lte", None)

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
            cicle_filter = CicloAtual.objects.filter(nome="Colheita")[0].ciclo
            safra_filter = CicloAtual.objects.filter(nome="Colheita")[0].safra

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
            .order_by("data_plantio")
        )
        
    def changelist_view(self, request, extra_context=None):
        request.GET = request.GET.copy()

        ciclo = request.GET.get("ciclo")
        safra = request.GET.get("safra")

        created_at_gte = request.GET.get("created_at_gte")
        created_at_lte = request.GET.get("created_at_lte")
        data_gte = request.GET.get("data_gte")
        data_lte = request.GET.get("data_lte")

        print("GET COMPLETO ORIGINAL:", dict(request.GET))
        print("created_at_gte:", created_at_gte)
        print("created_at_lte:", created_at_lte)
        print("data_gte:", data_gte)
        print("data_lte:", data_lte)

        # limpa parâmetros customizados antes do admin padrão processar
        clean_get = request.GET.copy()
        clean_get.pop("ciclo", None)
        clean_get.pop("safra", None)
        clean_get.pop("created_at_gte", None)
        clean_get.pop("created_at_lte", None)
        clean_get.pop("data_gte", None)
        clean_get.pop("data_lte", None)
        request.GET = clean_get

        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )

        safra_ciclo = CicloAtual.objects.filter(nome="Colheita")[0]
        safra_filter = safra_ciclo.safra.safra
        cicle_filter = safra_ciclo.ciclo.ciclo

        if ciclo and safra:
            safra_filter = safra.replace("_", "/")
            cicle_filter = ciclo

        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response

        # =========================================================
        # BASE DO PLANTIO -> ÁREA TOTAL (SEM FILTRO DE DATA/CRIADO)
        # =========================================================
        base_qs = (
            qs.filter(
                safra__safra=safra_filter,
                ciclo__ciclo=cicle_filter,
                finalizado_plantio=True,
                plantio_descontinuado=False,
                acompanhamento_medias=True,
            )
            .filter(~Q(variedade__cultura__cultura="Milheto"))
            .filter(~Q(variedade__cultura__cultura="Algodão"))
            .filter(~Q(id_farmbox__in=self.list_ids))
        )

        print("base_qs count:", base_qs.count())

        area_total_qs = (
            base_qs.values(
                "talhao__fazenda__nome",
                "variedade__cultura__cultura",
                "variedade__variedade",
            )
            .annotate(
                area_total=Coalesce(
                    Sum("area_colheita"),
                    Value(0),
                    output_field=DecimalField(),
                )
            )
            .order_by("talhao__fazenda__nome")
        )

        # =========================================================
        # ÁREA COLHIDA -> VEM DO EXTRATO DE COLHEITA
        # =========================================================
        colheita_extrato_qs = (
            ColheitaPlantioExtratoArea.objects.filter(
                ativo=True,
                plantio__safra__safra=safra_filter,
                plantio__ciclo__ciclo=cicle_filter,
                plantio__plantio_descontinuado=False,
                plantio__acompanhamento_medias=True,
            )
            .filter(~Q(plantio__variedade__cultura__cultura="Milheto"))
            .filter(~Q(plantio__variedade__cultura__cultura="Algodão"))
            .filter(~Q(plantio__id_farmbox__in=self.list_ids))
        )

        if created_at_gte or created_at_lte:
            created_q = build_created_filters(
                created_at_gte=created_at_gte,
                created_at_lte=created_at_lte,
                field_name="criados",
            )
            print("created_q area extrato:", created_q)
            colheita_extrato_qs = colheita_extrato_qs.filter(created_q)

        if data_gte or data_lte:
            data_q = build_date_filters(
                data_gte=data_gte,
                data_lte=data_lte,
                field_name="data_colheita",
            )
            print("data_q area extrato:", data_q)
            colheita_extrato_qs = colheita_extrato_qs.filter(data_q)

        print("colheita_extrato_qs count:", colheita_extrato_qs.count())

        area_colhida_qs = (
            colheita_extrato_qs.values(
                "plantio__talhao__fazenda__nome",
                "plantio__variedade__cultura__cultura",
                "plantio__variedade__variedade",
            )
            .annotate(
                area_finalizada=Coalesce(
                    Sum("area_colhida"),
                    Value(0),
                    output_field=DecimalField(),
                )
            )
            .order_by("plantio__talhao__fazenda__nome")
        )

        print("NEW AREA COLHIDA QS:::", area_colhida_qs)

        # =========================================================
        # JUNTA ÁREA TOTAL + ÁREA COLHIDA FILTRADA
        # =========================================================
        summary_dict = {}

        for item in area_total_qs:
            key = (
                item["talhao__fazenda__nome"],
                item["variedade__cultura__cultura"],
                item["variedade__variedade"],
            )
            summary_dict[key] = {
                "talhao__fazenda__nome": item["talhao__fazenda__nome"],
                "variedade__cultura__cultura": item["variedade__cultura__cultura"],
                "variedade__variedade": item["variedade__variedade"],
                "area_total": item["area_total"] or 0,
                "area_finalizada": 0,
            }

        for item in area_colhida_qs:
            key = (
                item["plantio__talhao__fazenda__nome"],
                item["plantio__variedade__cultura__cultura"],
                item["plantio__variedade__variedade"],
            )

            if key not in summary_dict:
                summary_dict[key] = {
                    "talhao__fazenda__nome": item["plantio__talhao__fazenda__nome"],
                    "variedade__cultura__cultura": item["plantio__variedade__cultura__cultura"],
                    "variedade__variedade": item["plantio__variedade__variedade"],
                    "area_total": 0,
                    "area_finalizada": 0,
                }

            summary_dict[key]["area_finalizada"] = item["area_finalizada"] or 0

        summary_list = list(summary_dict.values())

        print("summary_list len:", len(summary_list))

        response.context_data["summary_2"] = json.dumps(
            summary_list,
            cls=DjangoJSONEncoder,
        )

        response.context_data["colheita_2"] = json.dumps(
            get_cargas_model(
                safra_filter,
                cicle_filter,
                self.list_ids,
                created_at_gte=created_at_gte,
                created_at_lte=created_at_lte,
                data_gte=data_gte,
                data_lte=data_lte,
            ),
            cls=DjangoJSONEncoder,
        )

        response.context_data["created_at_gte"] = created_at_gte or ""
        response.context_data["created_at_lte"] = created_at_lte or ""
        response.context_data["data_gte"] = data_gte or ""
        response.context_data["data_lte"] = data_lte or ""

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
                # programa__isnull=False
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
    # fields = ["defensivo", "dose", "ativo", 'preco']
    fields = ["defensivo", "dose", "ativo"]
    autocomplete_fields = ["defensivo"]
    formset = AplicacoesProgramaInlineFormSet

    
    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)  # Add your custom CSS file here
        }


@admin.register(CotacaoDolar)
class CotacaoDolarAdmin(admin.ModelAdmin):
    list_display = ("data", "valor_formatado")

    def valor_formatado(self, obj):
        valor = obj.valor or 0
        valor_str = f"R$ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
        return valor_str

    valor_formatado.short_description = "Valor (R$)"

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

class EmailInline(admin.TabularInline):
    model = EmailAberturaST.projetos.through
    extra = 1

@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    inlines = [EmailInline]
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
        "storage_id_farmbox"
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
    search_fields = ("cultura",)           # <-- necessário pro autocomplete



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
            "Area Parcial",
            # "Area a Considerar",
            "lat",
            "long",
            "dap",
            "Area Saldo Carregar",
            "Area Aferida",
            "Saldo Plantar",
            "Data Prevista Colheita Real"
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
        "area_aferida",
        "data_prevista_colheita_real"
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
        data_prevista_colheita_real = plantio_detail.pop()
        time_delta_variedade_germinacao = plantio_detail[-2]
        area_aferida = plantio_detail.pop()
        area_aferida = "Sim" if area_aferida == True else "Não"
        print('area_aferida', area_aferida)
        val_11 = plantio_detail[11]
        val_12 = plantio_detail[12]
        
        area_plantada_math = val_12 if val_11 is not None and val_12 is not None and val_11 > 0 and val_12 > 0 else 0
        print('\n')
        print('plantio_detail[12]: ', plantio_detail[12])
        print('plantio_detail[11]: ', plantio_detail[11])
        print('\n')
        
        area_planejada_math = val_11 if val_11 is not None and val_12 is not None and val_11 > 0 and val_12 > 0 else 0
        saldo_plantar = area_planejada_math - area_plantada_math
        
        plantio_detail.pop()
        lat = ""
        lng = ""
        
        area_parcial_number = plantio_detail[16] if plantio_detail[16] else 0
        area_parcial = str(area_parcial_number).replace(".",",") if area_parcial_number else 0
        
        area_plantada_number = plantio_detail[12] if plantio_detail[12] else 0
        area_plantada = str(area_plantada_number).replace(".",",") if plantio_detail[20] == True else ' - '
        
        area_saldo_carregar = area_plantada_number - area_parcial_number
        
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
        plantio_detail.append(str(area_parcial).replace(".", ','))
        
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
        plantio_detail.append(str(area_saldo_carregar).replace(".", ','))
        plantio_detail.append(area_aferida)
        plantio_detail.append(str(saldo_plantar if saldo_plantar >= 1 else 0).replace(".", ','))
        plantio_detail.append(data_prevista_colheita_real)
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


class ExcludeOperacaoFilter(SimpleListFilter):
    title = 'Tipo de Defensivo'
    parameter_name = 'tipo_defensivo'

    def lookups(self, request, model_admin):
        return [
            ('sem_operacao', 'Todos exceto "Operação"'),
            ('so_operacao', 'Somente "Operação"'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'sem_operacao':
            return queryset.exclude(defensivo__tipo='operacao')
        elif self.value() == 'so_operacao':
            return queryset.filter(defensivo__tipo='operacao')
        return queryset

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

class PrecoPreenchidoFilter(admin.SimpleListFilter):
    title = "Preço"
    parameter_name = "preco_preenchido"

    def lookups(self, request, model_admin):
        return (
            ("com_preco", "Com Preço"),
            ("sem_preco", "Sem Preço"),
        )

    def queryset(self, request, queryset):
        if self.value() == "com_preco":
            return queryset.filter(preco__isnull=False).exclude(preco=0)
        elif self.value() == "sem_preco":
            return queryset.filter(models.Q(preco__isnull=True) | models.Q(preco=0))
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

class DefensivoIdFarmboxFilter(admin.SimpleListFilter):
    """
    Filtro para verificar se o defensivo associado à aplicação
    possui ou não um id_farmbox cadastrado.
    """
    # Título que aparecerá acima das opções do filtro na sidebar do admin.
    title = 'ID Farmbox do Defensivo'

    # Parâmetro que será usado na URL do admin (ex: ?id_farmbox_status=cadastrado)
    parameter_name = 'id_farmbox_status'

    def lookups(self, request, model_admin):
        """
        Retorna uma lista de tuplas. A primeira parte da tupla é o valor
        que será passado na URL, e a segunda é o texto que o usuário verá.
        """
        return (
            ('cadastrado', 'Com ID Farmbox'),
            ('nao_cadastrado', 'Sem ID Farmbox'),
        )

    def queryset(self, request, queryset):
        """
        Aplica o filtro no queryset principal com base no valor selecionado.
        """
        # self.value() retorna o valor selecionado pelo usuário ('cadastrado' ou 'nao_cadastrado')
        if self.value() == 'cadastrado':
            # Filtra por aplicações cujo defensivo tem um id_farmbox que NÃO é nulo.
            # Adicionamos .exclude() para o caso do campo ser um CharField e permitir strings vazias.
            return queryset.filter(defensivo__id_farmbox__isnull=False)

        if self.value() == 'nao_cadastrado':
            # Filtra por aplicações cujo defensivo tem um id_farmbox que É nulo OU uma string vazia.
            # Usamos Q objects para criar uma condição OR.
            return queryset.filter(
                Q(defensivo__id_farmbox__isnull=True)
            )
        
        # Se nenhum filtro for selecionado, retorna o queryset original
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

@admin.action(description="Gerar Formulário Plantio")
def gerar_formulario_plantio(self, request, queryset):
    # Otimização do queryset
    queryset = queryset.select_related(
        'safra',
        'ciclo',
        'talhao__fazenda__fazenda',  # acessa: p.talhao.fazenda.fazenda
        'variedade__cultura'         # acessa: p.variedade.cultura
    )
    
    ids_in_order = request.POST.getlist('_selected_action')
    id_to_obj = {str(obj.pk): obj for obj in queryset}
    ordered_queryset = [id_to_obj[pk] for pk in ids_in_order if pk in id_to_obj]
    
    # Token do usuário autenticado
    user_token = Token.objects.get(user=request.user)

    # Área total e dados dos plantios
    total_area = sum(p.area_colheita for p in queryset)
    plantios_data = [
        {"sought_area": float(p.area_colheita), "plantation_id": p.id_farmbox}
        for p in ordered_queryset
    ]

    # Dados do primeiro plantio (todos devem ter os mesmos dados de fazenda/safra nesse contexto)
    first = queryset[0]
    projeto_nome = first.talhao.fazenda.nome
    

    # Contexto para renderização
    context = dict(
        **self.admin_site.each_context(request),
        plantios=ordered_queryset,
        plantios_json=json.dumps(plantios_data),
        projeto_nome=projeto_nome.replace('Projeto', ''),
        total_area=total_area,
        action='gerar_formulario_plantio',
        YOUR_TOKEN=user_token,
    )

    return render(request, 'admin/gerar_formulario_plantio.html', context)

@admin.action(description="Abrir Aplicação no Farmbox")
def abrir_aplicacao_farmbox(self, request, queryset):
    # Otimização do queryset
    queryset = queryset.select_related(
        'safra',
        'ciclo',
        'talhao__fazenda__fazenda',  # acessa: p.talhao.fazenda.fazenda
        'variedade__cultura'         # acessa: p.variedade.cultura
    )
    
    ids_in_order = request.POST.getlist('_selected_action')
    id_to_obj = {str(obj.pk): obj for obj in queryset}
    ordered_queryset = [id_to_obj[pk] for pk in ids_in_order if pk in id_to_obj]
    
    # Token do usuário autenticado
    user_token = Token.objects.get(user=request.user)
    
    choices_tipo = dict(TIPO_CHOICES)
    whens_tipo = [When(tipo=key, then=Value(val)) for key, val in TIPO_CHOICES]

    defensivos = (
        Defensivo.objects
        .filter(id_farmbox__isnull=False, unidade_medida__isnull=False,ativo=True)
        .annotate(
            id_farmbox_str=F("id_farmbox"),
            tipo_display=Case(*whens_tipo, output_field=CharField()),
            )
        .values("id_farmbox_str", "produto", "unidade_medida", 'formulacao', 'tipo_display')
    )
    # Área total e dados dos plantios
    total_area = sum(p.area_colheita for p in queryset)
    plantios_data = [
        {"sought_area": float(p.area_colheita), "plantation_id": p.id_farmbox}
        for p in ordered_queryset
    ]
    
    programa_query = (
        Aplicacao.objects.select_related(
            "defensivo",
            "operacao",
            "operacao__programa",
            "operacao__programa__safra",
            "operacao__programa__ciclo",
            "operacao__programa__cultura",
        )
        .values(
            "defensivo__produto",
            "defensivo__tipo",
            "defensivo__id_farmbox",
            "dose",
            "operacao",
            "operacao__estagio",
            "operacao__prazo_dap",
            "operacao__programa",
            "operacao__programa__nome",
            "operacao__programa__safra__safra",
            "operacao__programa__ciclo__ciclo",
            "operacao__programa__cultura__cultura",
        )
        .filter(
            ativo=True,
        )
        .filter(operacao__programa__ativo=True)
    )
    
    agrupado = defaultdict(lambda: {"__meta__": {}, "__estagios__": defaultdict(list)})
    
    for r in programa_query:
        prog_id = r["operacao__programa"]
        estagio = r["operacao__estagio"] or "Sem estágio"
        prazo = r.get("operacao__prazo_dap")  # pode ser int/None

        if not agrupado[prog_id]["__meta__"]:
            agrupado[prog_id]["__meta__"] = {
                "id": prog_id,
                "nome": r["operacao__programa__nome"],
                "safra": r["operacao__programa__safra__safra"],
                "ciclo": r["operacao__programa__ciclo__ciclo"],
                "cultura": r["operacao__programa__cultura__cultura"],
            }

        # cria o bloco do estágio se não existir
        if estagio not in agrupado[prog_id]["__estagios__"]:
            agrupado[prog_id]["__estagios__"][estagio] = {"nome": estagio, "ord": prazo, "itens": []}
        else:
            # mantém o menor prazo (ou o primeiro) como critério de ordenação
            blk = agrupado[prog_id]["__estagios__"][estagio]
            if blk["ord"] is None or (prazo is not None and prazo < blk["ord"]):
                blk["ord"] = prazo

        agrupado[prog_id]["__estagios__"][estagio]["itens"].append({
            "produto": r["defensivo__produto"],
            "tipo": r["defensivo__tipo"],
            "id_farmbox": r["defensivo__id_farmbox"],
            "dose": float(r["dose"]) if r["dose"] is not None else None,
        })

    programas_data = []
    for prog_id, bloco in agrupado.items():
        estagios_list = list(bloco["__estagios__"].values())
        # ⬇️ ORDENA por ord (prazo_dap), nulos por último
        estagios_list.sort(key=lambda e: (e["ord"] is None, e["ord"]))
        programas_data.append({**bloco["__meta__"], "estagios": estagios_list})



    # Dados do primeiro plantio (todos devem ter os mesmos dados de fazenda/safra nesse contexto)
    first = queryset[0]
    projeto_nome = first.talhao.fazenda.nome
    charge_id = first.talhao.fazenda.fazenda.id_encarregado_farmbox
    response_id = first.talhao.fazenda.fazenda.id_responsavel_farmbox
    farm_id_farmbox = first.talhao.fazenda.id_farmbox
    harvest_id_farm = first.safra.id_farmbox

    # Contexto para renderização
    context = dict(
        **self.admin_site.each_context(request),
        plantios=ordered_queryset,
        plantios_json=json.dumps(plantios_data),
        projeto_nome=projeto_nome,
        defensivos=defensivos,
        total_area=total_area,
        action='abrir_aplicacao_farmbox',
        YOUR_TOKEN=user_token,
        CHARGE_ID=int(charge_id),
        RESPONSE_ID=int(response_id),
        FARM_ID=int(farm_id_farmbox),
        HARVEST_ID=int(harvest_id_farm),
        programa_data_json=mark_safe(json.dumps(programas_data)),  # passa como JSON seguro
    )

    return render(request, 'admin/abrir_aplicacao_farmbox.html', context)

@admin.action(description="📅 Visualizar cronograma do programa")
def acao_ver_cronograma_programa(self, request, queryset):
    if queryset.count() != 1:
        self.message_user(request, "Selecione apenas um item.", level='error')
        return

    obj = queryset.first()
    return redirect('admin:view_cronograma_programa', obj_id=obj.id)

class GerarKMLForm(AdminActionForm):  
    should_use_color = forms.BooleanField(
        required=False,
        label="Cor KML",
    )


@admin.register(Plantio)
class PlantioAdmin(ExtraButtonsMixin, AdminConfirmMixin, admin.ModelAdmin):
    actions = [
        export_plantio,
        area_aferida,
        abrir_aplicacao_farmbox,
        gerar_formulario_plantio,
        'update_data_prevista_plantio',
        'gerar_kml_aviacao',
        'zerar_plantio_para_replantio'
    ]
    show_full_result_count = False
    autocomplete_fields = ["talhao", "programa", "variedade"]
    action_form = GerarKMLForm

    TOTAL_C_2_CACHE_KEY = "admin_plantio_total_c_2"

    def get_total_c_2(self, force_refresh=False):
        """
        Carrega as colheitas de forma lazy e com cache.
        Evita query no startup do Django admin.
        """
        if force_refresh:
            cache.delete(self.TOTAL_C_2_CACHE_KEY)

        data = cache.get(self.TOTAL_C_2_CACHE_KEY)
        if data is None:
            data = list(
                Colheita.objects.values_list(
                    "plantio__id",
                    "peso_scs_limpo_e_seco",
                    "data_colheita"
                )
            )
            cache.set(self.TOTAL_C_2_CACHE_KEY, data, 60)
        return data

    @property
    def total_c_2(self):
        """
        Mantém compatibilidade com todo o código legado
        que usa modeladmin.total_c_2.
        """
        return self.get_total_c_2()

    class Media:
        css = {
            "all": ("admin/css/plantio_changelist.css",)
        }
        js = ('admin/js/colapsar-mapdetails.js',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'cronograma/<int:obj_id>/',
                self.admin_site.admin_view(self.view_cronograma_programa),
                name='view_cronograma_programa',
            ),
            path(
                'update-data-prevista/',
                self.admin_site.admin_view(self.update_data_prevista_view),
                name='update_data_prevista'
            ),
        ]
        return custom_urls + urls

    @admin.action(description="Zerar Para Replantio (com confirmação)")
    def zerar_plantio_para_replantio(self, request, queryset):
        """
        Passo 1: Mostrar confirmação
        Passo 2: Se confirmado, aplicar as mudanças e redirecionar de volta
        """
        if "confirm" not in request.POST:
            selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)

            base_ctx = self.admin_site.each_context(request)
            base_ctx["available_apps"] = self.admin_site.get_app_list(request)

            context = {
                **base_ctx,
                "title": "Confirmar: Zerar para Replantio",
                "queryset": queryset,
                "opts": self.model._meta,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "selected": selected,
                "select_across": request.POST.get("select_across") == "1",
                "action": "zerar_plantio_para_replantio",
                "index": request.POST.get("index", "0"),
            }
            return TemplateResponse(
                request,
                "admin/plantio/confirm_zerar_replantio.html",
                context,
            )

        try:
            select_across = request.POST.get("select_across") == "1"
            selected_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)

            if select_across:
                qs = queryset
            else:
                qs = self.model.objects.filter(pk__in=selected_ids)

            pks = list(qs.values_list("pk", flat=True))
            if not pks:
                self.message_user(request, "Nada selecionado.", level=messages.WARNING)
                return HttpResponseRedirect(request.get_full_path())

            FIELDS_TO_RESET = dict(
                inicializado_plantio=False,
                finalizado_plantio=False,
                finalizado_colheita=False,
                area_parcial=None,
                data_plantio=None,
                data_emergencia=None,
                veiculos_carregados=0,
                area_aferida=False,
                plantio_descontinuado=False,
                cronograma_programa=None,
                replantio=True,
                farmbox_update=False,
                data_prevista_plantio=None,
            )

            with transaction.atomic():
                desativados = (
                    PlantioExtratoArea.objects
                    .filter(plantio_id__in=pks, ativo=True)
                    .update(ativo=False)
                )

                atualizados = (
                    Plantio.objects
                    .filter(pk__in=pks)
                    .update(
                        **FIELDS_TO_RESET,
                        area_colheita=F("area_planejamento_plantio")
                    )
                )

                cache.clear()

            self.message_user(
                request,
                f"Zerado(s) {atualizados} Plantio(s) e desativado(s) {desativados} extrato(s). Cache limpo.",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect(request.get_full_path())

        except Exception as e:
            self.message_user(request, f"Erro ao zerar para replantio: {e}", level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    @admin.action(description="Gerar KML")
    def gerar_kml_aviacao(self, request, queryset):
        try:
            should_use_color = bool(request.POST.get("should_use_color"))

            values_qs = queryset.values(
                "map_geo_points",
                "talhao__id_talhao",
                "id_farmbox",
                "variedade__cultura__map_color",
            )

            kml_content = create_kml(values_qs, should_use_color)

            filename = f"kml-{timezone.now().strftime('%Y%m%d-%H%M%S')}.kml"
            resp = HttpResponse(
                kml_content,
                content_type="application/vnd.google-earth.kml+xml",
            )
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
            return resp

        except Exception as e:
            self.message_user(request, f"Erro ao gerar KML: {e}", level=messages.ERROR)

    def update_data_prevista_plantio(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        url = reverse('admin:update_data_prevista')
        current_url = request.get_full_path()
        query = urlencode({
            'ids': ','.join(str(pk) for pk in selected),
            'next': current_url
        })
        return redirect(f"{url}?{query}")
    update_data_prevista_plantio.short_description = "Atualizar Dados em Lote"

    def _enqueue_farmbox_call(self, id_farmbox, data_str, variedade_id, cultura_id):
        t = Thread(
            target=self._safe_update_farmbox_data,
            args=(id_farmbox, data_str, variedade_id, cultura_id),
            daemon=True
        )
        t.start()

    def _safe_update_farmbox_data(self, id_farmbox, data_str, variedade_id, cultura_id):
        try:
            update_farmbox_data(id_farmbox, data_str, variedade_id, cultura_id)
        except Exception:
            logger.exception("Falha no update_farmbox_data (id_farmbox=%s)", id_farmbox)


    def update_data_prevista_view(self, request):
        print("Entrou na view custom de update")

        next_url = request.GET.get('next') or request.POST.get('next') or '..'
        ids = request.GET.get('ids', '')

        if request.method == 'POST':
            raw_ids = request.POST.getlist("row_plantio_ids")
            pks = []
            invalid_ids = []

            for raw in raw_ids:
                try:
                    clean = int(str(raw).replace(".", "").strip())
                    pks.append(clean)
                except Exception:
                    invalid_ids.append(raw)

            print("IDs limpos:", pks)
            print("IDs inválidos:", invalid_ids)
        else:
            raw_ids = [pk for pk in ids.split(',') if pk]

            pks = []
            for raw in raw_ids:
                try:
                    pks.append(int(str(raw).replace(".", "").strip()))
                except Exception:
                    pass

        queryset = self.model.objects.filter(pk__in=pks).select_related(
            'programa',
            'variedade',
            'variedade__cultura',
            'talhao',
            'talhao__fazenda',
        )

        total_area = queryset.aggregate(
            total_area_colheita=Sum('area_colheita')
        )['total_area_colheita']

        if request.method == 'POST':
            print("POST RECEBIDO")
            print("GET ids no POST:", request.GET.get('ids'))
            print("POST:", request.POST)

            form = UpdateDataPrevistaPlantioForm(request.POST)

            if not form.is_valid():
                print("FORM ERRORS:", form.errors)
                self.message_user(
                    request,
                    f"Form inválido: {form.errors}",
                    level=messages.ERROR
                )
            else:
                novo_programa = form.cleaned_data.get('programa')
                nova_variedade = form.cleaned_data.get('variedade')

                clear_prog = form.cleaned_data.get('_clear_programa')
                sent_prog = form.cleaned_data.get('_sent_programa')

                clear_var = form.cleaned_data.get('_clear_variedade')
                sent_var = form.cleaned_data.get('_sent_variedade')

                should_update_on_farm = form.cleaned_data.get('should_update_on_farm')

                row_plantio_ids = request.POST.getlist("row_plantio_ids")
                per_row_dates = {}
                invalid_rows = []

                for row_id_raw in row_plantio_ids:
                    row_id_key = str(row_id_raw).replace(".", "").strip()
                    raw_value = (request.POST.get(f"row_data_prevista_plantio_{row_id_raw}") or "").strip()

                    print("row bruto:", row_id_raw, "row limpo:", row_id_key, "raw_value:", raw_value)

                    if not raw_value:
                        per_row_dates[row_id_key] = None
                        continue

                    try:
                        per_row_dates[row_id_key] = datetime.strptime(raw_value, "%d/%m/%Y").date()
                    except ValueError:
                        invalid_rows.append(row_id_key)

                print("per_row_dates:", per_row_dates)

                if invalid_rows:
                    self.message_user(
                        request,
                        f"Existem datas inválidas nas linhas: {', '.join(invalid_rows)}.",
                        level=messages.ERROR
                    )
                else:
                    updated_count = 0

                    for instance in queryset:
                        old_programa = instance.programa
                        old_variedade = instance.variedade

                        final_date = per_row_dates.get(str(instance.pk), None)

                        changed = False

                        if instance.data_prevista_plantio != final_date:
                            print(
                                f"Plantio {instance.pk} alterando data de "
                                f"{instance.data_prevista_plantio} para {final_date}"
                            )
                            instance.data_prevista_plantio = final_date
                            changed = True

                        if clear_prog:
                            if instance.programa is not None or instance.cronograma_programa is not None:
                                instance.programa = None
                                instance.cronograma_programa = None
                                changed = True
                        elif sent_prog and novo_programa:
                            if old_programa != novo_programa:
                                print(
                                    'Programa alterado: ',
                                    'antes =', old_programa.id if old_programa else None,
                                    'depois =', novo_programa.id
                                )
                                instance.programa = novo_programa
                                instance.cronograma_programa = None
                                changed = True

                        if clear_var:
                            if instance.variedade is not None:
                                instance.variedade = None
                                changed = True
                        elif sent_var and nova_variedade:
                            if old_variedade != nova_variedade:
                                print(
                                    'Variedade alterada: ',
                                    'antes =', old_variedade.id if old_variedade else None,
                                    'depois =', nova_variedade.id
                                )
                                instance.variedade = nova_variedade
                                changed = True

                        if changed:
                            instance.save()
                            updated_count += 1

                            if should_update_on_farm:
                                transaction.on_commit(
                                    lambda i=instance: self._enqueue_farmbox_call(
                                        i.id_farmbox,
                                        str(i.data_prevista_plantio) if i.data_prevista_plantio else None,
                                        i.variedade.id_farmbox if i.variedade else None,
                                        i.variedade.cultura.id_farmbox if (i.variedade and i.variedade.cultura) else None,
                                    )
                                )

                    self.message_user(request, f'{updated_count} registros atualizados com sucesso.')
                    return redirect(next_url)
        else:
            form = UpdateDataPrevistaPlantioForm()

        context = dict(
            self.admin_site.each_context(request),
            form=form,
            queryset=queryset,
            total_area_selected=total_area,
            title='Atualizar Data Prevista de Plantio',
            next_url=next_url,
            ids=ids,
        )
        return render(request, 'admin/update_data_prevista.html', context)



    def view_cronograma_programa(self, request, obj_id):
        plantio = get_object_or_404(Plantio, id=obj_id)
        cronograma_raw = plantio.cronograma_programa or []
        cultura_nome = plantio.variedade.cultura.cultura
        variedade_nome = plantio.variedade.variedade
        referer = request.META.get("HTTP_REFERER", "/admin/")

        cronograma = []
        for etapa in cronograma_raw:
            etapa["data_prevista"] = etapa.pop("data prevista", None)
            for p in etapa.get("produtos", []):
                p["quantidade_aplicar"] = ""
                try:
                    dose = float(p.get("dose", 0))
                    p["quantidade_aplicar"] = round(float(plantio.area_colheita) * dose, 3)
                except Exception:
                    pass
            cronograma.append(etapa)

        cronograma.sort(key=lambda x: x.get("dap", -9999))

        context = dict(
            **self.admin_site.each_context(request),
            object=plantio,
            cultura_nome=cultura_nome,
            variedade_nome=variedade_nome,
            cronograma=cronograma,
            title=f"{plantio.talhao}",
            voltar_url=referer
        )
        return render(request, "admin/view_cronograma.html", context)

    @admin.action(description="Colher o Plantio")
    def finalize_plantio(self, request, queryset):
        queryset.update(finalizado_colheita=True)
        cargas = self.total_c_2

        for obj in queryset:
            print("colheita finalizada")

            filtered_list = [x[2] for x in cargas if obj.id == x[0]]
            sorted_list = sorted(filtered_list)
            closed_date = None
            if len(sorted_list) > 0:
                closed_date = sorted_list[0]
            else:
                today = str(datetime.now()).split(" ")[0].strip()
                closed_date = today

            total_filt_list = sum(
                [(x[1] * 60) for x in cargas if obj.id == x[0]]
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
                    str_resp = (
                        f'Alterado no FARMBOX - {resp_obj["farm_name"]} - {resp_obj["name"]} - '
                        f'{resp_obj["harvest_name"]}-{resp_obj["cycle"]} - Produtividade: '
                        f'{resp_obj["productivity"]} - Variedade: {resp_obj["variety_name"]} - '
                        f'Area: {resp_obj["area"]}'
                    )
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
        cache.delete(self.TOTAL_C_2_CACHE_KEY)
        self.message_user(request, "Dados da Colheita Atualizado")
        print("dados atualizados com sucesso!!")
        return HttpResponseRedirectToReferrer(request)

    def get_ordering(self, request):
        return ["data_plantio"]

    def get_queryset(self, request):
        qs = (
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
                "programa",
            )
            .prefetch_related("programa__variedade")
        )

        qs = qs.annotate(
            sort_date=Coalesce("data_plantio", "data_prevista_plantio"),
            is_null_both=Case(
                When(
                    Q(data_plantio__isnull=True) & Q(data_prevista_plantio__isnull=True),
                    then=Value(1),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by(
            "is_null_both",
            "sort_date",
            "talhao__id_talhao",
        )

        return qs

    def get_search_results(self, request, queryset, search_term):
        ciclo_filter = CicloAtual.objects.filter(nome="Colheita").first()
        ciclo_filter_plantio = CicloAtual.objects.filter(nome="Plantio").first()

        negate = False
        term = search_term

        if search_term and search_term.startswith("!"):
            negate = True
            term = search_term[1:].strip()

        if not negate:
            queryset, use_distinct = super().get_search_results(
                request, queryset, term
            )
        else:
            use_distinct = False

        print("resquest_Path", request.path)
        model_request = request.GET.get("model_name")
        print("model request: ", model_request)

        if model_request and model_request == "plantioextratoarea":
            queryset = queryset.filter(
                # ciclo__ciclo__in=["2", "3"],
                ciclo=ciclo_filter_plantio.ciclo,
                # safra__safra="2025/2026",
                safra=ciclo_filter_plantio.safra,
                finalizado_colheita=False,
                plantio_descontinuado=False,
                programa__isnull=False,
            )

            if negate and term:
                q = Q()
                for field in self.search_fields:
                    q |= Q(**{f"{field}__icontains": term})
                queryset = queryset.exclude(q)

            if not queryset.exists():
                return queryset.none(), use_distinct

            return queryset, use_distinct

        if request.path == "/admin/autocomplete/" and ciclo_filter:
            queryset = queryset.filter(
                ciclo=ciclo_filter.ciclo,
                finalizado_plantio=True,
                finalizado_colheita=False,
                plantio_descontinuado=False,
            )

            if negate and term:
                q = Q()
                for field in self.search_fields:
                    q |= Q(**{f"{field}__icontains": term})
                queryset = queryset.exclude(q)

            if not queryset.exists():
                return queryset.none(), use_distinct

            return queryset, use_distinct

        if negate and term:
            q = Q()
            for field in self.search_fields:
                q |= Q(**{f"{field}__icontains": term})

            queryset = queryset.exclude(q)

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
        "inicializado_plantio",
        "finalizado_plantio",
        "finalizado_colheita",
        "plantio_descontinuado",
        "talhao__fazenda__fazenda",
        "programa__nome",
        "talhao__modulo",
        "variedade",
        "modificado",
        "area_aferida",
        "acompanhamento_medias"
    )

    list_display = (
        "talhao",
        "cronograma_link",
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
        "get_data_prev_col_real",
        "get_description_finalizado_colheita",
        "get_total_colheita_cargas_kg",
        "get_total_prod",
        "get_data_primeira_carga",
        "get_data_ultima_carga",
        "get_total_colheita_cargas",
        "get_dias_ciclo",
        "get_description_descontinuado_plantio",
        "area_aferida",
        "area_parcial",
        "acompanhamento_medias",
        "id_farmbox",
    )

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
                        "pk"
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
                    ("area_aferida",),
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
                    ("data_prevista_colheita", "data_prevista_plantio", 'data_prevista_colheita_real'),
                    ("plantio_descontinuado",),
                    ("farmbox_update",),
                    ("acompanhamento_medias",),
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
        "pk"
    )

    @admin.display(description="🗓️")
    def cronograma_link(self, obj):
        url = reverse('admin:view_cronograma_programa', args=[obj.id])
        return format_html(
            '<a href="{}" title="Ver Cronograma">🗓️</a>',
            url
        )

    def save_model(self, request, obj, form, change):
        print(obj)
        print(self)
        print("form Plantio")
        print("Valor Atual: ")

        cargas = self.total_c_2

        if form.initial:
            if form.initial["data_plantio"] != obj.data_plantio:
                obj.cronograma_programa = None

            if (
                form.initial["finalizado_colheita"] == False
                and form.instance.finalizado_colheita == True
            ):
                print("Colheita Finalizada")

                filtered_list = [x[2] for x in cargas if obj.id == x[0]]
                sorted_list = sorted(filtered_list)
                closed_date = None
                if len(sorted_list) > 0:
                    closed_date = sorted_list[0]
                else:
                    today = str(datetime.now()).split(" ")[0].strip()
                    closed_date = today

                total_filt_list = sum(
                    [(x[1] * 60) for x in cargas if obj.id == x[0]]
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
                        str_resp = (
                            f'Alterado no FARMBOX - {resp_obj["farm_name"]} - {resp_obj["name"]} - '
                            f'{resp_obj["harvest_name"]}-{resp_obj["cycle"]} - Produtividade: '
                            f'{resp_obj["productivity"]} - Variedade: {resp_obj["variety_name"]} - '
                            f'Area: {resp_obj["area"]}'
                        )
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

            if form.initial['plantio_descontinuado'] == False and form.instance.plantio_descontinuado == True:
                print('valor foi alterado para descontinuado')
                PlantioExtratoArea.objects.filter(plantio=obj.pk).update(ativo=False)

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

    def get_data_primeira_carga(self, obj):
        cargas = self.total_c_2
        filtered_list = [x[2] for x in cargas if obj.id == x[0]]
        sorted_list = sorted(filtered_list)
        if len(sorted_list) > 0:
            return date_format(
                sorted_list[0], format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return "-"
    get_data_primeira_carga.short_description = "1ª Carga"

    def get_data_ultima_carga(self, obj):
        cargas = self.total_c_2
        filtered_list = [x[2] for x in cargas if obj.id == x[0]]
        sorted_list = sorted(filtered_list)
        if len(sorted_list) > 0:
            return date_format(
                sorted_list[-1], format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return "-"
    get_data_ultima_carga.short_description = "últ. Carga"

    def get_total_colheita_cargas(self, obj):
        cargas = self.total_c_2
        filtered_list = [x[1] for x in cargas if obj.id == x[0]]
        return len(filtered_list)
    get_total_colheita_cargas.short_description = "Cargas"

    def get_total_colheita_cargas_kg(self, obj):
        cargas = self.total_c_2
        filtered_list = [(x[1] * 60) for x in cargas if obj.id == x[0]]
        peso_total = sum(filtered_list) if sum(filtered_list) > 0 else " - "
        return peso_total
    get_total_colheita_cargas_kg.short_description = "Peso Carr."

    def get_total_prod(self, obj):
        cargas = self.total_c_2
        total_filt_list = sum([(x[1] * 60) for x in cargas if obj.id == x[0]])
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

    def get_data_prev_col_real(self, obj):
        if obj.data_prevista_colheita_real:
            return date_format(
                obj.data_prevista_colheita_real, format="SHORT_DATE_FORMAT", use_l10n=True
            )
        else:
            return " - "
    get_data_prev_col_real.short_description = "Data Prev. Col. Real"

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

    def check_var_on_programa_list(self, obj):
        if obj.programa and obj.variedade:
            ins_in_programa = obj.programa.variedade.filter(pk=obj.variedade.pk).exists()
            return ins_in_programa
    check_var_on_programa_list.boolean = True
    check_var_on_programa_list.short_description = "Variedade / Programa"
    

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
            "Nota Fiscal",
            "id FarmTruck"
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
        "nota_fiscal",
        "id_farmtruck"
        
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
    actions = [export_cargas,'duplicar_registro']
    class Media:
        js = ('admin/js/colapsar-observacao.js',)

    def get_urls(self):
        urls = super().get_urls()
        # my_urls = [path(r"^upload_csv/$", self.upload_csv, name="upload_csv")]
        my_urls = [
            path("upload_csv/", self.upload_csv, name="upload_csv"),
            path('<pk>/duplicate/', self.admin_site.admin_view(self.duplicate_view), name='colheita_duplicate'),
            ]

        return my_urls + urls

    urls = property(get_urls)
    
    def duplicar_registro(self, request, queryset):
        # só permite duplicar 1 por vez, mas pode adaptar pra múltiplos
        obj = queryset.first()
        return redirect(f'./{obj.pk}/duplicate/')

    duplicar_registro.short_description = "Duplicar registro selecionado"

    def duplicate_view(self, request, pk):
        obj = self.get_object(request, pk)
        initial_pairs = []

        for field in obj._meta.fields:
            # campos que NÃO queremos copiar
            if field.name in ['id', 'pk', 'plantio']:
                continue
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                continue

            # ForeignKey precisa usar o <field>_id
            if isinstance(field, models.ForeignKey):
                value = getattr(obj, f"{field.name}_id")
                if value:
                    initial_pairs.append(f"{field.name}={value}")
                continue
            
            # DateField
            if isinstance(field, models.DateField):
                value = getattr(obj, field.name)
                if value:
                    formatted = value.strftime('%d/%m/%Y')
                    initial_pairs.append(f"{field.name}={formatted}")
                continue  # << já tratou, pula pro próximo campo

            # Qualquer outro campo
            value = getattr(obj, field.name)
            if value is not None:
                initial_pairs.append(f"{field.name}={value}")

        initial_data = "&".join(initial_pairs)
        return redirect(f"../../add/?{initial_data}")

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
                    ("ticket", "op", 'nota_fiscal'),
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
        ("Observações", {
            "fields": (("observacao",)),
            "classes": ["collapse"],  # Força lista
            }),
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
        "get_umidade",
        "get_desconto_umidade",
        "impureza",
        "desconto_impureza",
        # "peso_scs_limpo_e_seco",
        # "bandinha",
        # "desconto_bandinha",
        "peso_liquido",
        "peso_scs_liquido",
        "nota_fiscal"
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
        "nota_fiscal",
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
            start_time = time.time()
            user_id = Token.objects.get(user=request.user)
            form = SomeModelForm(request.POST, request.FILES)
            if form.is_valid():
                data_file = request.FILES["csv_file"]
                data_json = json.load(data_file)
                request_start = time.time()
                
                print('startTime: ', request_start)
                
                resp = save_from_protheus_logic(data_json, user_id)
                request_end = time.time()
                print(f"Tempo da requisição: {round(request_end - request_start, 2)} segundos")
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
                            lambda x: f"Romaneio: {x['romaneio']} - {x['projeto']}: {x['parcela']} - Ticket: {x['ticket']} <br/> {x['error']}",
                            failed_loads,
                        )
                    )
                    messages.add_message(request, messages.WARNING, msg)
                    for failed, item in zip(failed_format, failed_loads):
                        if item['error'] == "ID NAO ENCONTRADO":
                            print('estamos entrando aqui')
                            messages.add_message(request, messages.WARNING, mark_safe(failed))  # amarelo
                        else:
                            messages.add_message(request, messages.ERROR, mark_safe(failed))  # vermelho
            # Fim da contagem de tempo
            end_time = time.time()

            # Tempo total em segundos
            total_time = end_time - start_time
            print(f"Tempo total: {total_time:.2f} segundos")
            
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))

    # def changelist_view(self, *args, **kwargs):
    #     view = super().changelist_view(*args, **kwargs)
    #     print(self)
    #     # view.context_data["submit_csv_form"] = SomeModelForm
    #     return view

    def get_umidade(self, obj):
        if obj.umidade and obj.umidade > 0 :
            return obj.umidade
        else:
            return " - "
    get_umidade.short_description = "Umidade"
    
    def get_desconto_umidade(self, obj):
        if obj.umidade and obj.umidade > 0 :
            return obj.desconto_umidade
        else:
            return " - "
    get_desconto_umidade.short_description = "Desc. Umidade"
    
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
    
    form = ProgramaAdminForm
    
                    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            # Só executa na criação
            duplicar = form.cleaned_data.get("duplicar")
            keep_price = form.cleaned_data.get("keep_price")
            print('keep price', keep_price)
            old_program = form.cleaned_data.get("programa_base")

            if duplicar and old_program:
                print("Programa base:", old_program)
                print("Novo programa (obj):", obj)
                # Aqui você chama sua função de duplicar passando os modelos
                try:
                    print('aqui vamos tentar Duplicar o Prgorama')
                    duplicate_existing_operations_program_and_applications(old_program, obj, Operacao, Aplicacao , keep_price)
                    self.message_user(request, "Programa duplicado com sucesso.", messages.SUCCESS)
                except Exception as e:
                    self.message_user(request, f"Erro ao duplicar programa: {e}", messages.ERROR)
                    
    def get_queryset(self, request):
        return (
            super(ProgramaAdmin, self)
            .get_queryset(request)
            .select_related("safra", "ciclo")
        )

    show_full_result_count = False
    readonly_fields = ["modificado"]
    filter_horizontal = ('variedade',)  # Field name

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj:  # Está editando, não criando
            # Remove a seção que tem 'duplicar'
            fieldsets = [
                fs for fs in fieldsets if 'duplicar' not in str(fs)
            ]
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:
            # Nunca incluir campos que só existem na criação
            if 'duplicar' in readonly:
                readonly.remove('duplicar')
            if 'programa_base' in readonly:
                readonly.remove('programa_base')
        return readonly
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
            "Duplicando o Programa",
            {
                "fields": (
                    ("duplicar", "programa_base", 'keep_price'),  
                )
            },
        ),
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
    
    class Media:
        js = [
            "admin/js/vendor/jquery/jquery.js",
            "admin/js/vendor/select2/select2.full.js",
            "admin/js/core.js",
        ]
        css = {
            "all": [
                "admin/css/switch_toggle.css",
                "admin/css/vendor/select2/select2.css",
                "admin/css/widgets.css",
            ]
        }

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

def format_brl(valor):
    if not valor:
        return ' - '
    """Formata um Decimal/float como R$ em estilo brasileiro."""
    valor = valor or Decimal("0.00")
    return f"{valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def export_programa(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="Programas.csv"'
    response.write(codecs.BOM_UTF8)
    writer = csv.writer(response, delimiter=";")

    # Cabeçalhos da planilha
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
            "Preço",
            "Moeda",
            "Valor Final",
            "Valor Aplicação",
            "Cotação Usada (se USD)",
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
            "preco",
            "moeda",
            "valor_final",
            "valor_aplicacao",
        )
        .order_by("operacao__prazo_dap", "defensivo__tipo", "defensivo__produto")
        .filter(ativo=True, operacao__ativo=True)
    )

    for op in operacoes:
        op = list(op)

        # Extrair valores relevantes para cálculo
        preco = op[12] or Decimal("0")
        moeda = op[13]
        valor_final = op[14] or Decimal("0")

        # Dose como string com vírgula
        op[5] = "0" if op[5] is None else str(op[5]).replace(".", ",")

        # Formatar valores
        op[12] = format_brl(preco)
        op[14] = format_brl(valor_final)
        op[15] = format_brl(op[15])  # valor_aplicacao

        # Calcular cotação usada
        if moeda == "USD" and preco:
            try:
                cotacao = valor_final / preco
                cotacao_formatado = f"{cotacao:.4f}".replace(".", ",")
            except DivisionByZero:
                cotacao_formatado = ""
        else:
            cotacao_formatado = ""

        op.append(cotacao_formatado)

        writer.writerow(op)

    return response


export_programa.short_description = "Exportar para CSV"

def is_valid_uuid(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False



# =========================================================
# ✅ MAQUINA ADMIN (completo)
# =========================================================
@admin.register(Maquina)
class MaquinaAdmin(admin.ModelAdmin):
    save_on_top = True
    show_full_result_count = False
    list_per_page = 50
    date_hierarchy = "modificado"

    # performance
    list_select_related = ("fazenda",)

    # UX
    list_display = (
        "nome",
        "tipo",
        "referencia",
        "patrimonio",
        "chassi",
        "get_fazenda",
        "ativo",
        "modificado",
    )

    list_filter = (
        "tipo",
        "ativo",
        "fazenda",
        "modificado",
    )

    search_fields = (
        "nome",
        "tipo",
        "referencia",
        "patrimonio",
        "chassi",
        "fazenda__nome",
    )

    ordering = ("nome",)

    # se FazendaAdmin tiver search_fields, autocomplete fica ótimo
    autocomplete_fields = ("fazenda",)

    fieldsets = (
        ("Identificação", {
            "fields": ("nome", "tipo", "ativo"),
        }),
        ("Referências", {
            "fields": ("referencia", "patrimonio", "chassi"),
        }),
        ("Localização (opcional)", {
            "fields": ("fazenda",),
            "description": "Use para mapear onde a máquina normalmente fica. Pode deixar em branco.",
        }),
        ("Observações", {
            "fields": ("observacao",),
        }),
        ("Auditoria", {
            "fields": ("criados", "modificado"),
        }),
    )

    readonly_fields = ("criados", "modificado")

    actions = ("marcar_ativo", "marcar_inativo")

    @admin.action(description="Marcar selecionadas como ATIVAS")
    def marcar_ativo(self, request, queryset):
        n = queryset.update(ativo=True)
        self.message_user(
            request,
            f"{n} máquina(s) marcada(s) como ativa(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Marcar selecionadas como INATIVAS")
    def marcar_inativo(self, request, queryset):
        n = queryset.update(ativo=False)
        self.message_user(
            request,
            f"{n} máquina(s) marcada(s) como inativa(s).",
            level=messages.WARNING,
        )

    def get_fazenda(self, obj):
        return obj.fazenda.nome if obj.fazenda else "—"
    get_fazenda.short_description = "Fazenda"
    
    
# =========================================================
# ✅ OPERACAO ADMIN (ajustada p/ máquina)
# =========================================================
@admin.register(Operacao)
class OperacaoAdmin(admin.ModelAdmin):

    class Media:
        css = {
            "all": ("admin/css/highlight_deleted_inlines.css",)
        }
        js = (
            "admin/js/highlight_deleted_inlines.js",
            "https://cdn.jsdelivr.net/npm/sweetalert2@11",
        )

    show_full_result_count = False
    save_on_top = True
    list_per_page = 50
    date_hierarchy = "modificado"

    inlines = [AplicacoesProgramaInline]

    # ✅ melhora performance do changelist (evita N+1)
    list_select_related = (
        "programa",
        "programa__cultura",
        "maquina",
        "maquina__fazenda",
    )

    # ✅ autocomplete pra programa e máquina (bom demais no admin)
    autocomplete_fields = ("programa", "maquina")

    # ✅ inclui máquina nas buscas
    search_fields = [
        "programa__nome",
        "programa__nome_fantasia",
        "programa__cultura__cultura",
        "estagio",
        "prazo_dap",
        "obs",
        "maquina__nome",
        "maquina__tipo",
        "maquina__placa",
        "maquina__patrimonio",
        "maquina__fazenda__nome",
    ]

    list_display = (
        "estagio",
        "programa",
        "get_prazo_dap",
        "get_cultura_description",
        "get_maquina_display",
        "get_obs_description",
        "ativo",
    )

    list_filter = [
        ProgramaFilter,
        "programa__safra",
        "programa__ciclo",
        "maquina",
        "maquina__tipo",
        "modificado",
        "ativo",
    ]

    ordering = (
        "programa",
        "prazo_dap",
    )

    fieldsets = (
        ("Programa / Estágio", {
            "fields": ("programa", "estagio", "operacao_numero", "ativo"),
        }),
        ("Prazos", {
            "fields": ("prazo_dap", "prazo_emergencia", "base_dap", "base_emergencia"),
        }),
        ("Base operação anterior", {
            "fields": ("base_operacao_anterior", "dias_base_operacao_anterior"),
        }),
        ("Máquina (1 por estágio)", {
            "fields": ("maquina",),
            "description": "Opcional. Define qual máquina executa esta operação/estágio.",
        }),
        ("Visual / Observações", {
            "fields": ("map_color", "obs", "observacao"),
        }),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(programa__ativo=True)
            .select_related("programa", "programa__cultura", "maquina", "maquina__fazenda")
        )

    # =========================
    # THREAD/TASK (mantido, só organizado)
    # =========================
    @staticmethod
    def processar_operacao_em_background(
        task_id,
        query,
        current_op,
        produtos,
        changed_dap,
        newDap,
        nome_estagio_alterado,
        estagio_alterado,
    ):
        close_old_connections()  # fundamental em thread
        task = None
        started_at = timezone.now()

        try:
            task = BackgroundTaskStatus.objects.get(task_id=task_id)
            task.status = "running"
            if hasattr(task, "started_at"):
                task.started_at = started_at
            task.save(update_fields=["status"] + (["started_at"] if hasattr(task, "started_at") else []))

            admin_form_alter_programa_and_save(
                query,
                current_op,
                produtos,
                changed_dap,
                newDap,
                nome_estagio_alterado,
                estagio_alterado,
            )

            task.status = "done"
            if hasattr(task, "result"):
                task.result = {"ok": True}
        except Exception as e:
            if task:
                task.status = "failed"
                if hasattr(task, "result"):
                    task.result = {"error": str(e)}
        finally:
            if task:
                if hasattr(task, "ended_at"):
                    task.ended_at = timezone.now()
                    task.save(update_fields=["status"] + (["result"] if hasattr(task, "result") else []) + (["ended_at"] if hasattr(task, "ended_at") else []))
                else:
                    task.save(update_fields=["status"] + (["result"] if hasattr(task, "result") else []))
            close_old_connections()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if request.session.get("executou_task") and "task_id" in request.session:
            task_id = request.session.pop("task_id", None)
            extra_context["task_id"] = task_id
            request.session.pop("executou_task", None)
            request.session.modified = True
        return super().changelist_view(request, extra_context=extra_context)

    # ⚠️ mantém seu padrão: salvar “pai” via save_formset
    def save_model(self, request, obj, form, change):
        # não salva aqui, salva no save_formset
        pass

    def save_formset(self, request, form, formset, change):
        programa_nome = form.instance.programa.nome

        # evita rodar duas tasks ao mesmo tempo pro mesmo programa
        exists_running = BackgroundTaskStatus.objects.filter(
            task_name=programa_nome,
            status__in=["pending", "running"],
        ).exists()
        if exists_running:
            raise ValidationError(
                f"Já existe uma tarefa em andamento para o programa '{programa_nome}'. "
                f"Aguarde a finalização antes de salvar novamente."
            )

        # salva pai + filhos
        form.instance.save()
        formset.save()

        # detecta mudança de DAP
        changed_dap = False
        if form.initial:
            changed_dap = form.initial.get("prazo_dap") != form.instance.prazo_dap
        newDap = form.instance.prazo_dap

        # detecta mudança do nome do estágio
        nome_estagio_alterado = False
        estagio_alterado = ""
        current_op = form.instance.estagio

        if form.initial and "estagio" in form.initial:
            estagio_original = (form.initial.get("estagio") or "").strip()
            estagio_novo = (form.instance.estagio or "").strip()
            if estagio_original and estagio_novo and estagio_original != estagio_novo:
                nome_estagio_alterado = True
                current_op = estagio_original
                estagio_alterado = estagio_novo

        # quando ativo, dispara task de recalcular indices/agenda
        if form.instance.ativo is True:
            query = Aplicacao.objects.select_related("operacao").filter(
                ativo=True,
                operacao=form.instance,
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

            current_program = form.instance.programa
            current_query = Plantio.objects.filter(
                programa=current_program,
                inicializado_plantio=True,
            )

            task_id = str(uuid.uuid4())
            BackgroundTaskStatus.objects.create(
                task_id=task_id,
                task_name=programa_nome,
                status="pending",
            )

            Thread(
                target=self.processar_operacao_em_background,
                args=(
                    task_id,
                    current_query,
                    current_op,
                    produtos,
                    changed_dap,
                    newDap,
                    nome_estagio_alterado,
                    estagio_alterado,
                ),
                daemon=True,
            ).start()

            request.session["task_id"] = str(task_id)
            request.session["executou_task"] = True
            request.session.modified = True

        # quando desativa, remove índices
        if form.instance.ativo is False:
            current_op = form.instance.estagio
            current_program = form.instance.programa
            current_query = Plantio.objects.filter(
                programa=current_program,
                inicializado_plantio=True,
            )
            admin_form_remove_index(current_query, current_op)

    # =========================
    # helpers display
    # =========================
    def get_cultura_description(self, obj):
        return obj.programa.cultura.cultura if obj.programa and obj.programa.cultura else "—"
    get_cultura_description.short_description = "Cultura"

    def get_prazo_dap(self, obj):
        return obj.prazo_dap
    get_prazo_dap.short_description = "DAP"

    def get_obs_description(self, obj):
        if obj.observacao or obj.obs:
            base = obj.obs or obj.observacao or ""
            base = str(base)
            return f"{base[:20]}..."
        return " - "
    get_obs_description.short_description = "Obs"

    def get_maquina_display(self, obj):
        if not getattr(obj, "maquina", None):
            return "—"
        if getattr(obj.maquina, "fazenda", None):
            return f"{obj.maquina.nome} ({obj.maquina.fazenda.nome})"
        return obj.maquina.nome
    get_maquina_display.short_description = "Máquina"
@admin.register(Defensivo)
class DefensivoAdmin(admin.ModelAdmin):
    list_display = ("produto", "tipo", 'id_farmbox', 'unidade_medida')
    # ordering = ["operacao__estagio", "produto"]
    ordering = ["produto"]
    search_fields = ["produto", "tipo", 'id_farmbox']
    list_filter = ("tipo",)
    show_full_result_count = False
    exclude = ('observacao',)  # <-- aqui você informa o campo a excluir


class TipoDefensivoFilter(SimpleListFilter):
    title = "Tipo Defensivo"
    parameter_name = "tipo_defensivo"

    def lookups(self, request, model_admin):
        return (
            ("insumos", "Somente insumos (≠ Operação)"),
            ("operacao", "Somente Operação"),
        )

    def queryset(self, request, queryset):
        if self.value() == "insumos":
            return queryset.exclude(defensivo__tipo="operacao")

        if self.value() == "operacao":
            return queryset.filter(defensivo__tipo="Operação")

        return queryset

def _normalizar_nome_produto(nome):
    return " ".join((nome or "").strip().upper().split())
@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    actions = [export_programa, "substituir_produto_em_lote", "editar_precos_em_lote"]

    show_full_result_count = False
    autocomplete_fields = ["defensivo", "operacao"]

    list_display = (
        "defensivo",
        "operacao_link",
        "get_programa",
        "get_safra",
        "get_ciclo",
        "get_estagio",
        "dose",
        "preco",
        "moeda",
        "valor_final",
        "valor_aplicacao",
        "ativo",
    )

    search_fields = [
        "defensivo__produto",
        "operacao__estagio",
        "operacao__programa__nome",
        "operacao__programa__nome_fantasia",
    ]

    list_filter = [
        "ativo",
        "operacao__programa__safra",
        "operacao__programa__ciclo",
        "operacao__programa__cultura",
        ProgramaAplicacaoFilter,
        PrecoPreenchidoFilter,
        DefensivoIdFarmboxFilter,
        TipoDefensivoFilter,
    ]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "defensivo",
                "operacao",
                "operacao__programa",
                "operacao__programa__safra",
                "operacao__programa__ciclo",
                "operacao__programa__cultura",
            )
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "editar-precos-em-lote/",
                self.admin_site.admin_view(self.editar_precos_em_lote_view),
                name="diamante_aplicacao_editar_precos_em_lote",
            ),
        ]
        return custom_urls + urls

    def operacao_link(self, obj):
        if not obj.operacao_id:
            return "-"

        url = reverse(
            f"admin:{obj.operacao._meta.app_label}_{obj.operacao._meta.model_name}_change",
            args=[obj.operacao_id],
        )
        return format_html('<a href="{}">{}</a>', url, obj.operacao)

    operacao_link.short_description = "Operação"
    operacao_link.admin_order_field = "operacao"

    def get_programa(self, obj):
        return obj.operacao.programa.nome if obj.operacao and obj.operacao.programa else "-"
    get_programa.short_description = "Programa"

    def get_safra(self, obj):
        prog = getattr(obj.operacao, "programa", None)
        return prog.safra.safra if prog and prog.safra else "-"
    get_safra.short_description = "Safra"

    def get_ciclo(self, obj):
        prog = getattr(obj.operacao, "programa", None)
        return prog.ciclo.ciclo if prog and prog.ciclo else "-"
    get_ciclo.short_description = "Ciclo"

    def get_estagio(self, obj):
        return obj.operacao.estagio if obj.operacao else "-"
    get_estagio.short_description = "Estágio"

    def _get_action_queryset(self, request, queryset):
        selected_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        select_across = request.POST.get("select_across") == "1"

        if select_across:
            return queryset

        valid_ids = []
        for _id in selected_ids:
            try:
                valid_ids.append(int(_id))
            except (ValueError, TypeError):
                continue

        return self.model.objects.filter(pk__in=valid_ids)

    def _get_produto_origem_da_selecao(self, qs):
        itens_origem = list(
            qs.values("defensivo_id", "defensivo__produto")
            .order_by("defensivo_id")
            .distinct()
        )

        if not itens_origem:
            return None, [], "empty"

        nomes_normalizados = {
            _normalizar_nome_produto(item["defensivo__produto"])
            for item in itens_origem
            if item.get("defensivo__produto")
        }

        if len(itens_origem) == 1:
            produto_origem_id = itens_origem[0]["defensivo_id"]
            produto_origem = Defensivo.objects.filter(pk=produto_origem_id).first()
            return produto_origem, itens_origem, None

        if len(nomes_normalizados) == 1:
            produto_origem_id = itens_origem[0]["defensivo_id"]
            produto_origem = Defensivo.objects.filter(pk=produto_origem_id).first()
            return produto_origem, itens_origem, None

        return None, itens_origem, "multiple"

    @admin.action(description="Substituir produto em lote")
    def substituir_produto_em_lote(self, request, queryset):
        qs = (
            self._get_action_queryset(request, queryset)
            .select_related("defensivo", "operacao", "operacao__programa")
            .order_by("id")
        )

        produto_origem, itens_origem, erro_origem = self._get_produto_origem_da_selecao(qs)

        if erro_origem == "empty" or not produto_origem:
            self.message_user(
                request,
                "Nenhuma aplicação válida foi selecionada.",
                level=messages.WARNING,
            )
            return HttpResponseRedirect(request.get_full_path())

        if erro_origem == "multiple":
            nomes_exibicao = sorted({
                (item.get("defensivo__produto") or "").strip()
                for item in itens_origem
                if item.get("defensivo__produto")
            })

            self.message_user(
                request,
                "Foram encontrados múltiplos produtos diferentes na seleção: "
                + " | ".join(nomes_exibicao),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.get_full_path())

        total_registros = qs.count()

        if "apply" in request.POST:
            form = BulkReplaceAplicacaoForm(
                request.POST,
                produto_origem=produto_origem,
            )

            if form.is_valid():
                produto_destino = form.cleaned_data["produto_destino"]
                alterar_dose = form.cleaned_data["alterar_dose"]
                nova_dose = form.cleaned_data["nova_dose"]
                zerar_custo = form.cleaned_data["zerar_custo"]

                atualizados = 0
                conflitos = 0
                ignorados = 0
                programas_afetados = set()

                with transaction.atomic():
                    for app in qs:
                        dose_final = nova_dose if alterar_dose else app.dose

                        conflito = Aplicacao.objects.filter(
                            operacao=app.operacao,
                            defensivo=produto_destino,
                            ativo=app.ativo,
                            dose=dose_final,
                        ).exclude(pk=app.pk).exists()

                        if conflito:
                            conflitos += 1
                            continue

                        mudou_algo = False

                        if app.defensivo_id != produto_destino.id:
                            app.defensivo = produto_destino
                            mudou_algo = True

                        if alterar_dose and app.dose != dose_final:
                            app.dose = dose_final
                            mudou_algo = True

                        if zerar_custo and (app.preco or 0) != 0:
                            app.preco = 0
                            mudou_algo = True

                        if not mudou_algo:
                            ignorados += 1
                            continue

                        app.save()
                        atualizados += 1

                        if app.operacao and app.operacao.programa_id:
                            programas_afetados.add(app.operacao.programa_id)

                tasks_disparadas = 0
                tasks_ignoradas = 0

                for programa_id in programas_afetados:
                    programa = Programa.objects.filter(pk=programa_id).first()
                    if not programa:
                        continue

                    task_name = programa.nome

                    exists_running = BackgroundTaskStatus.objects.filter(
                        task_name=task_name,
                        status__in=["pending", "running"],
                    ).exists()

                    if exists_running:
                        tasks_ignoradas += 1
                        continue

                    task_id = str(uuid.uuid4())
                    BackgroundTaskStatus.objects.create(
                        task_id=task_id,
                        task_name=task_name,
                        status="pending",
                    )

                    Thread(
                        target=processar_programa_em_background,
                        args=(task_id, programa_id),
                        daemon=True,
                    ).start()

                    tasks_disparadas += 1
                    request.session["task_id"] = str(task_id)
                    request.session["executou_task"] = True
                    request.session.modified = True

                if atualizados:
                    self.message_user(
                        request,
                        f"{atualizados} aplicação(ões) atualizada(s) com sucesso.",
                        level=messages.SUCCESS,
                    )

                if conflitos:
                    self.message_user(
                        request,
                        f"{conflitos} aplicação(ões) não foram alteradas por conflito de unicidade.",
                        level=messages.WARNING,
                    )

                if ignorados:
                    self.message_user(
                        request,
                        f"{ignorados} aplicação(ões) já estavam no estado final e foram ignoradas.",
                        level=messages.INFO,
                    )

                if tasks_disparadas:
                    self.message_user(
                        request,
                        f"{tasks_disparadas} tarefa(s) de reprocessamento de programa disparada(s).",
                        level=messages.SUCCESS,
                    )

                if tasks_ignoradas:
                    self.message_user(
                        request,
                        f"{tasks_ignoradas} programa(s) já tinham tarefa em andamento e foram ignorados.",
                        level=messages.WARNING,
                    )

                return HttpResponseRedirect(request.get_full_path())

        else:
            form = BulkReplaceAplicacaoForm(produto_origem=produto_origem)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Substituir produto em lote",
            "form": form,
            "queryset": qs[:20],
            "total_registros": total_registros,
            "produto_origem": produto_origem,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "selected": request.POST.getlist(helpers.ACTION_CHECKBOX_NAME),
            "select_across": request.POST.get("select_across") == "1",
            "action": "substituir_produto_em_lote",
        }

        return render(
            request,
            "admin/diamante/aplicacao/substituir_produto_em_lote.html",
            context,
        )
        
        

    @admin.action(description="Editar preços em lote")
    def editar_precos_em_lote(self, request, queryset):
        qs = (
            self._get_action_queryset(request, queryset)
            .select_related(
                "defensivo",
                "operacao",
                "operacao__programa",
                "operacao__programa__safra",
                "operacao__programa__ciclo",
            )
            .order_by("operacao__programa__nome", "operacao__estagio", "defensivo__produto", "id")
        )

        ids = list(qs.values_list("id", flat=True))

        if not ids:
            self.message_user(
                request,
                "Nenhuma aplicação válida foi selecionada.",
                level=messages.WARNING,
            )
            return HttpResponseRedirect(request.get_full_path())

        base_url = reverse("admin:diamante_aplicacao_editar_precos_em_lote")
        query_string = urlencode({
            "ids": ",".join(map(str, ids)),
            "next": request.get_full_path(),
        })

        return redirect(f"{base_url}?{query_string}")


    def editar_precos_em_lote_view(self, request):
        ids_raw = request.POST.get("ids") or request.GET.get("ids", "")
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("admin:diamante_aplicacao_changelist")

        ids = []
        for item in (ids_raw or "").split(","):
            item = (item or "").strip()
            if not item:
                continue
            try:
                ids.append(int(item))
            except (ValueError, TypeError):
                continue

        qs = (
            self.model.objects.filter(pk__in=ids)
            .select_related(
                "defensivo",
                "operacao",
                "operacao__programa",
                "operacao__programa__safra",
                "operacao__programa__ciclo",
            )
            .order_by("operacao__programa__nome", "operacao__estagio", "defensivo__produto", "id")
        )

        total_registros = qs.count()

        if not total_registros:
            self.message_user(
                request,
                "Nenhuma aplicação válida foi encontrada para edição.",
                level=messages.WARNING,
            )
            return redirect(next_url)

        if request.method == "POST":
            atualizados = 0
            ignorados = 0
            erros = 0
            programas_afetados = set()

            # agora o topo também vale no backend
            bulk_preco_raw = request.POST.get("bulk_preco_submit")
            bulk_moeda = request.POST.get("bulk_moeda_submit")

            bulk_preco = None
            has_bulk_preco = False
            has_bulk_moeda = bool(bulk_moeda)

            try:
                if bulk_preco_raw not in [None, ""]:
                    bulk_preco = Decimal(str(bulk_preco_raw).replace(",", "."))
                    has_bulk_preco = True
            except (InvalidOperation, ValueError):
                self.message_user(
                    request,
                    "O preço informado no preenchimento em massa é inválido.",
                    level=messages.ERROR,
                )
                context = {
                    **self.admin_site.each_context(request),
                    "opts": self.model._meta,
                    "title": "Editar preços em lote",
                    "queryset": qs,
                    "total_registros": total_registros,
                    "moeda_choices": self.model._meta.get_field("moeda").choices,
                    "ids": ",".join(map(str, ids)),
                    "next": next_url,
                    "changelist_url": next_url,
                }
                return render(
                    request,
                    "admin/diamante/aplicacao/editar_precos_em_lote.html",
                    context,
                )

            with transaction.atomic():
                for app in qs:
                    prefix = f"row_{app.pk}_"

                    # prioridade:
                    # 1) se vier preenchimento em massa, usa ele
                    # 2) senão usa o valor individual da linha
                    if has_bulk_preco:
                        preco_novo = bulk_preco
                    else:
                        preco_raw = request.POST.get(f"{prefix}preco")
                        try:
                            if preco_raw in [None, ""]:
                                preco_novo = None
                            else:
                                preco_novo = Decimal(str(preco_raw).replace(",", "."))
                        except (InvalidOperation, ValueError):
                            erros += 1
                            continue

                    if has_bulk_moeda:
                        moeda_nova = bulk_moeda
                    else:
                        moeda_nova = request.POST.get(f"{prefix}moeda")

                    preco_antigo = app.preco
                    moeda_antiga = app.moeda

                    mudou_algo = False

                    if preco_antigo != preco_novo:
                        app.preco = preco_novo
                        mudou_algo = True

                    if moeda_nova and moeda_antiga != moeda_nova:
                        app.moeda = moeda_nova
                        mudou_algo = True

                    if not mudou_algo:
                        ignorados += 1
                        continue

                    app.save()
                    atualizados += 1


            if atualizados:
                self.message_user(
                    request,
                    f"{atualizados} aplicação(ões) atualizada(s) com sucesso.",
                    level=messages.SUCCESS,
                )

            if ignorados:
                self.message_user(
                    request,
                    f"{ignorados} aplicação(ões) não tinham alteração e foram ignoradas.",
                    level=messages.INFO,
                )

            if erros:
                self.message_user(
                    request,
                    f"{erros} aplicação(ões) tiveram erro de preenchimento no preço.",
                    level=messages.WARNING,
                )

            return redirect(next_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Editar preços em lote",
            "queryset": qs,
            "total_registros": total_registros,
            "moeda_choices": self.model._meta.get_field("moeda").choices,
            "ids": ",".join(map(str, ids)),
            "next": next_url,
            "changelist_url": next_url,
        }

        return render(
            request,
            "admin/diamante/aplicacao/editar_precos_em_lote.html",
            context,
        )
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
    list_filter = (
        ("criados", DateFieldListFilter),  # Filters by the 'criados' date field
    )

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
    
    list_display = ("st_numero", "get_data", "st_fazenda")
    search_fields = ("criados", 'st_numero', 'st_fazenda')
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
            return date_format(obj.criados, format="DATETIME_FORMAT", use_l10n=True)
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
    
    
    def save_model(self, request, obj, form, change):
        # Se for edição de uma instância existente
        if obj.pk and change:
            previous = self.model.objects.get(pk=obj.pk)

            # Verifica se estava ativo e agora foi desativado
            if previous.ativo and not obj.ativo:
                total_area = self.model.objects.filter(
                    plantio=obj.plantio, ativo=True
                ).exclude(pk=obj.pk).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )['total_area_plantada'] or 0

                if total_area > obj.plantio.area_planejamento_plantio:
                    self.message_user(
                        request,
                        f"⚠️ A área total já apontada ({total_area:.2f}) excede a área planejada ({obj.plantio.area_planejamento_plantio:.2f}).",
                        level=messages.WARNING
                    )

                # Exemplo de atualização
                obj.plantio.area_colheita = min(total_area, obj.plantio.area_planejamento_plantio)
                obj.plantio.save()

        super().save_model(request, obj, form, change)
    
    
    list_display = ("talhao_description", "get_data", "safra_description", "cultura_description", "variedade_description", "area_plantada","related_link", 'get_finalizado_plantio', 'ativo')
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
    
    def get_finalizado_plantio(self, obj):
        if obj.finalizado_plantio:
            return True
        return False

    get_finalizado_plantio.boolean = True
    get_finalizado_plantio.short_description = "Plantio Fin."
    
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
    # Exibição na listagem
    list_display = (
        "codigo_planejamento", 
        "projeto", 
        "safra", 
        "ciclo", 
        "criados",  # Assumindo que vem da classe Base
    )
    
    # Filtros laterais (essencial para dados agrícolas)
    list_filter = ("safra", "ciclo", "projeto", "criados")
    
    # Campo de busca (busca por código ou nome do projeto relacionado)
    
    
    # Ordenação padrão
    ordering = ("-criados",)
    
    
    
    
    # Organização dentro do formulário de edição
    fieldsets = (
        ("Informações Identificadoras", {
            "fields": ("codigo_planejamento", "projeto")
        }),
        ("Sazonalidade", {
            "fields": ("safra", "ciclo")
        }),
        ("Metadados", {
            "fields": ("criados", "modificado"), # Assumindo campos da classe Base
            "classes": ("collapse",), # Deixa recolhido por padrão
        }),
    )

    readonly_fields = ("criados", "modificado")
    
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
    list_filter = ['safra', 'ciclo', 'destino', 'variedade']
    ordering = ['-data_envio']  # Descending order by date
    
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

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)

        # Replace 1 and 2 with the actual IDs you want to set as defaults
        initial['safra'] = 4
        initial['ciclo'] = 3

        return initial
    
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
    get_data_envio.short_description = "Data Envio"
    
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
    

from datetime import timedelta

@admin.register(BackgroundTaskStatus)
class BackgroundTaskStatusAdmin(admin.ModelAdmin):
    list_display = [
        'task_id',
        'formated_created',
        'task_name',
        'status',
        'formatted_started_at',
        'formatted_ended_at',
        'task_duration'
    ]

    def formatted_started_at(self, obj):
        if obj.started_at:
            return obj.started_at.strftime('%d/%m/%Y %H:%M:%S')
        return "-"
    formatted_started_at.short_description = "Início"

    def formatted_ended_at(self, obj):
        if obj.ended_at:
            return obj.ended_at.strftime('%d/%m/%Y %H:%M:%S')
        return "-"
    formatted_ended_at.short_description = "Fim"

    def task_duration(self, obj):
        if obj.started_at and obj.ended_at:
            duration = obj.ended_at - obj.started_at
            # Formata como H:MM:SS
            return str(timedelta(seconds=int(duration.total_seconds())))
        return "-"
    task_duration.short_description = "Duração"
    
    def formated_created(self, obj):
        if obj.criados:
            return obj.criados.strftime('%d/%m/%Y %H:%M:%S')
        return "-"
    formated_created.short_description = "Data"
    
    

@admin.register(EmailAberturaST)
class EmailAberturaSTAdmin(admin.ModelAdmin):
    list_display = ["email", "get_projetos", 'get_tipos', 'ativo']
    filter_horizontal = ["projetos", 'atividade']

    def get_projetos(self, obj):
        return ", ".join([p.nome.replace('Projeto ', '').split()[0] for p in obj.projetos.all()])

    get_projetos.short_description = "Projetos"
    
    def get_tipos(self, obj):
        return ", ".join([p.tipo for p in obj.atividade.all()])

    get_tipos.short_description = "Atividades"
    
    
@admin.register(TiposAtividadeEmails)
class TiposAtividadesEmailsAdmin(admin.ModelAdmin):
    list_display = ['tipo']
    
# list_display = ("criados", "projeto", "email", 'ativo')





@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    # ---- colunas da lista ----
    list_display = (
        "nome",
        "descricao",
        "get_cultura",
        "get_variedade",
        "target_day",
        "lead_days",
        "get_janela_dias",
        "get_intervalo_datas_br",
        "plantios_na_janela",
        "get_freq",
        "get_weekday_label",
        "send_email",
        "send_whatsapp",
        "ativo",
        "get_criados_br",
        "get_modificado_br",
    )
    list_display_links = ("nome",)
    list_per_page = 50
    ordering = ("-ativo", "nome")

    # ---- filtros/busca ----
    list_filter = (
        "ativo",
        "freq",
        "weekday",
        "send_email",
        "send_whatsapp",
        "cultura",
        "variedade",
    )
    search_fields = (
        "nome",
        "descricao",
        "variedade__variedade",
        "variedade__cultura__cultura",
    )
    autocomplete_fields = ("cultura", "variedade")

    # ---- somente leitura e layout ----
    readonly_fields = ("criados", "modificado")
    fieldsets = (
        ("Identificação", {
            "fields": (
                ("ativo",),
                ("nome", "descricao"),
                ("observacao",),
            )
        }),
        ("Filtro (escopo da regra)", {
            "fields": (
                ("cultura", "variedade"),
            )
        }),
        ("Janela (dias após o plantio)", {
            "fields": (
                ("target_day", "lead_days"),
            )
        }),
        ("Recorrência e canais", {
            "fields": (
                ("freq", "weekday"),
                ("send_email", "send_whatsapp"),
            )
        }),
        ("Sistema", {
            "fields": (
                ("criados", "modificado"),
            )
        }),
    )

    # ---- otimização da queryset ----
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Evita N+1 em cultura/variedade e não traz campos grandes desnecessários
        return (
            qs.select_related("cultura", "variedade", "variedade__cultura")
              .defer("observacao")
        )

    # ---- helpers de exibição ----
    def get_cultura(self, obj):
        return obj.cultura.cultura if obj.cultura_id else "—"
    get_cultura.short_description = "Cultura"

    def get_variedade(self, obj):
        return obj.variedade.variedade if obj.variedade_id else "—"
    get_variedade.short_description = "Variedade"

    def get_janela_dias(self, obj):
        start, end = obj.window_days
        return f"{start}–{end} dias"
    get_janela_dias.short_description = "Janela (dias)"

    def get_intervalo_datas_br(self, obj):
        today = timezone.localdate()
        dmin, dmax = obj.window_date_range_for_today(today)
        dmin_br = date_format(dmin, format="SHORT_DATE_FORMAT", use_l10n=True)
        dmax_br = date_format(dmax, format="SHORT_DATE_FORMAT", use_l10n=True)
        return f"{dmin_br} – {dmax_br}"
    get_intervalo_datas_br.short_description = "Intervalo (datas plantio)"

    def plantios_na_janela(self, obj):
        """
        Mostra contagem dos plantios que caem na janela HOJE.
        (Se tiver muitas regras/plantios, considere cachear ou anotar via batch)
        """
        today = timezone.localdate()
        return obj.filtered_plantios_in_window(today=today).count()
    plantios_na_janela.short_description = "Plantios na janela"

    def get_freq(self, obj):
        # exibe o label da choice
        return dict(obj.FREQ_CHOICES).get(obj.freq, obj.freq)
    get_freq.short_description = "Frequência"

    def get_weekday_label(self, obj):
        mapa = {
            0: "Seg",
            1: "Ter",
            2: "Qua",
            3: "Qui",
            4: "Sex",
            5: "Sáb",
            6: "Dom",
        }
        return mapa.get(obj.weekday, obj.weekday)
    get_weekday_label.short_description = "Dia (semana)"

    def get_criados_br(self, obj):
        return date_format(obj.criados, format="SHORT_DATETIME_FORMAT", use_l10n=True)
    get_criados_br.short_description = "Criado em"

    def get_modificado_br(self, obj):
        return date_format(obj.modificado, format="SHORT_DATETIME_FORMAT", use_l10n=True)
    get_modificado_br.short_description = "Atualizado em"

from django.contrib import admin
from django.http import JsonResponse, HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.core.serializers.json import DjangoJSONEncoder
import json

from .models import FarmPolygon


@admin.register(FarmPolygon)
class FarmPolygonAdmin(admin.ModelAdmin):
    change_list_template = "admin/teste_farmpolygon.html"

    list_display = (
        "name",
        "farm_name",
        "user_name",
        "mode_badge",
        "status_badges",
        "area_ha",
        "perimeter_pretty",
        "points_count",
        "updated_at",
        "row_actions",
    )

    list_filter = (
        "mode",
        "is_closed",
        "is_active",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "farm_name",
        "user_name",
        "submitted_email",
        "observation",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "points_pretty",
        "map_preview",
    )

    fieldsets = (
        ("Dados principais", {
            "fields": (
                "name",
                "farm_name",
                "user_name",
                "submitted_email",
                "mode",
                "is_closed",
                "is_active",
            )
        }),
        ("Geometria", {
            "fields": (
                "map_preview",
                "points",
                "points_pretty",
                "area_m2",
                "perimeter_m",
            )
        }),
        ("Extras", {
            "fields": (
                "observation",
            )
        }),
        ("Datas", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:polygon_id>/preview/",
                self.admin_site.admin_view(self.preview_polygon_view),
                name="diamante_farmpolygon_preview",
            ),
            path(
                "<int:polygon_id>/export-kml/",
                self.admin_site.admin_view(self.export_kml_view),
                name="diamante_farmpolygon_export_kml",
            ),
        ]
        return custom_urls + urls

    def preview_polygon_view(self, request, polygon_id):
        obj = self.get_object(request, polygon_id)
        if not obj:
            return JsonResponse({"error": "Polígono não encontrado"}, status=404)

        return JsonResponse(
            {
                "id": obj.id,
                "name": obj.name,
                "farm_name": obj.farm_name,
                "user_name": obj.user_name,
                "submitted_email": obj.submitted_email,
                "mode": obj.get_mode_display() if hasattr(obj, "get_mode_display") else obj.mode,
                "is_closed": obj.is_closed,
                "is_active": obj.is_active,
                "area_m2": float(obj.area_m2) if obj.area_m2 is not None else None,
                "perimeter_m": float(obj.perimeter_m) if obj.perimeter_m is not None else None,
                "observation": obj.observation or "",
                "points": obj.points or [],
                "edit_url": reverse(
                    f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
                    args=[obj.pk]
                ),
                "kml_url": reverse("admin:diamante_farmpolygon_export_kml", args=[obj.pk]),
            },
            encoder=DjangoJSONEncoder,
        )

    def export_kml_view(self, request, polygon_id):
        obj = self.get_object(request, polygon_id)
        if not obj:
            return HttpResponse("Polígono não encontrado", status=404)

        points = obj.points or []
        if not points:
            return HttpResponse("Polígono sem pontos", status=400)

        coordinates = []
        for p in points:
            lng = p.get("lng") or p.get("longitude") or p.get("lon")
            lat = p.get("lat") or p.get("latitude")
            if lat is None or lng is None:
                continue
            coordinates.append(f"{lng},{lat},0")

        if obj.is_closed and coordinates and coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])

        geometry = (
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            + " ".join(coordinates)
            + "</coordinates></LinearRing></outerBoundaryIs></Polygon>"
            if obj.is_closed
            else "<LineString><coordinates>"
            + " ".join(coordinates)
            + "</coordinates></LineString>"
        )

        kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{obj.name}</name>
    <Placemark>
      <name>{obj.name}</name>
      <description>Fazenda: {obj.farm_name}</description>
      {geometry}
    </Placemark>
  </Document>
</kml>'''

        response = HttpResponse(kml, content_type="application/vnd.google-earth.kml+xml")
        response["Content-Disposition"] = f'attachment; filename="{obj.name}.kml"'
        return response

    def mini_map(self, obj):
        return format_html(
            '<div class="fp-mini-map" data-points=\'{}\' data-closed="{}"></div>',
            json.dumps(obj.points or [], ensure_ascii=False),
            "true" if obj.is_closed else "false",
        )
    mini_map.short_description = "Mapa"

    def points_count(self, obj):
        return len(obj.points or [])
    points_count.short_description = "Pontos"

    def area_ha(self, obj):
        if not obj.area_m2:
            return "-"
        return f"{float(obj.area_m2) / 10000:.2f} ha"
    area_ha.short_description = "Área"

    def perimeter_pretty(self, obj):
        if not obj.perimeter_m:
            return "-"
        return f"{float(obj.perimeter_m):.2f} m"
    perimeter_pretty.short_description = "Perímetro"

    def points_pretty(self, obj):
        return json.dumps(obj.points or [], indent=2, ensure_ascii=False)
    points_pretty.short_description = "Points formatado"

    def mode_badge(self, obj):
        color = "#2563eb" if obj.mode == FarmPolygon.MODE_MANUAL else "#7c3aed"
        label = obj.get_mode_display() if hasattr(obj, "get_mode_display") else obj.mode
        return format_html(
            '<span class="fp-badge" style="background:{}15;color:{};">{}</span>',
            color,
            color,
            label,
        )
    mode_badge.short_description = "Modo"

    def status_badges(self, obj):
        closed = (
            '<span class="fp-badge" style="background:#16a34a15;color:#16a34a;">Fechado</span>'
            if obj.is_closed else
            '<span class="fp-badge" style="background:#f59e0b15;color:#b45309;">Aberto</span>'
        )
        active = (
            '<span class="fp-badge" style="background:#16a34a15;color:#16a34a;">Ativo</span>'
            if obj.is_active else
            '<span class="fp-badge" style="background:#ef444415;color:#b91c1c;">Inativo</span>'
        )
        return format_html('{} {}', format_html(closed), format_html(active))
    status_badges.short_description = "Status"

    def row_actions(self, obj):
        preview_url = reverse("admin:diamante_farmpolygon_preview", args=[obj.pk])
        kml_url = reverse("admin:diamante_farmpolygon_export_kml", args=[obj.pk])
        edit_url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])

        return format_html(
            '''
            <div class="fp-row-actions">
                <button type="button" class="button fp-preview-btn" data-preview-url="{}">Preview</button>
                <a class="button fp-kml-btn" href="{}">KML</a>
                <a class="button fp-edit-btn" href="{}">Editar</a>
            </div>
            ''',
            preview_url,
            kml_url,
            edit_url,
        )
    row_actions.short_description = "Ações"

    def map_preview(self, obj):
        if not obj.pk:
            return "Salve o objeto para visualizar o mapa."
        preview_url = reverse("admin:diamante_farmpolygon_preview", args=[obj.pk])
        return format_html(
            '''
            <div class="fp-form-preview-wrap">
                <div class="fp-form-preview-header">
                    <strong>Preview do polígono</strong>
                </div>
                <div id="fp-form-map"
                     class="fp-form-map"
                     data-preview-url="{}"></div>
            </div>
            ''',
            preview_url,
        )
    map_preview.short_description = "Mapa"