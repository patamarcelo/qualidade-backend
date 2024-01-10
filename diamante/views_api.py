from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page


# Create your views here.

from .serializers import (
    TalhaoSerializer,
    PlantioSerializer,
    DefensivoSerializer,
    AplicacaoSerializer,
    ColheitaSerializer,
    VisitasSerializer,
    RegistroVisitasSerializer,
)

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth.models import User
from rest_framework.renderers import JSONRenderer
from rest_framework import generics


import json
from django.http import JsonResponse
from django.core.serializers import serialize
from django.db.models import Q, Sum, DecimalField, Count, FilteredRelation
import datetime
from dateutil.relativedelta import relativedelta
from decimal import *
from django.db.models import Q
from .utils import (
    get_dap,
    get_prev_app_date,
    get_quantidade_aplicar,
    get_base_date,
    get_index_dict_estagio,
)

import qualidade_project.mongo_api as mongo_api

# from qualidade_project.settings import db_name
from .models import (
    Talhao,
    Projeto,
    Variedade,
    Plantio,
    Safra,
    Ciclo,
    Defensivo,
    Aplicacao,
    Operacao,
    Colheita,
    Programa,
    PlannerPlantio,
    Deposito,
    Visitas,
    RegistroVisitas,
)

from functools import reduce


import openpyxl
import json
import csv


from colorama import init as colorama_init
from colorama import Fore
from colorama import Style

import os
from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
import math

from django.db.models.functions import Round


from rest_framework.decorators import api_view, permission_classes
from django.db.models.functions.datetime import ExtractMonth, ExtractYear

import requests


# --------------------- --------------------- START DEFENSIVOS MONGO API --------------------- --------------------- #


# --------------------- --------------------- END DEFENSIVOS MONGO API --------------------- --------------------- #


# --------------------- --------------------- START TALHAO API --------------------- --------------------- #


s_dict = {
    "2022/2023": 1,
    "2023/2024": 2,
}

c_dict = {"1": 3, "2": 4, "3": 5}


class TalaoViewSet(viewsets.ModelViewSet):
    queryset = Talhao.objects.all().order_by("id_talhao")
    serializer_class = TalhaoSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    @action(detail=True, methods=["POST"])
    def save_talhao(self, request, pk=None):
        if request.user.is_authenticated:
            if "talhao" in request.data:
                file = request.FILES["talhao"]
                entradas = openpyxl.load_workbook(file, data_only=True)
                worksheet = entradas["talhao"]
                produtos = []
                projetos = Projeto.objects.all()
                for col in worksheet.iter_rows(min_row=1, max_col=26, max_row=30000):
                    if col[1].value != None and col[0].value != "FAZENDA":
                        fazenda = col[0].value
                        id_id = col[1].value
                        descricao = col[2].value
                        parcela = col[3].value
                        area = col[4].value
                        modulo = col[5].value
                        projeto = [x for x in projetos if x.id_d == fazenda][0]
                        try:
                            novo_talhao = Talhao(
                                id_talhao=parcela,
                                id_unico=id_id,
                                fazenda=projeto,
                                area_total=area,
                                modulo=modulo,
                            )
                            novo_talhao.save()
                            # produto = {
                            #     "fazenda": fazenda,
                            #     "id_unico": id,
                            #     "descricao": descricao,
                            #     "id_talhao": parcela,
                            #     "area_total": area,
                            #     "modulo": modulo,
                            # }
                            # produtos.append(produto)
                        except Exception as e:
                            print(f"Erro ao salvar o talhao {parcela} - {e}")
                # for i in produtos:
                #     print(i)
            qs = Talhao.objects.all()
            # Talhao.objects.aggregate(Sum('area_total'))
            serializer = TalhaoSerializer(qs, many=True)
            response = {
                "msg": f"Dados alterados com sucesso",
                "Quantidade Cadastrada": "Cadastros",
                "dados": serializer.data,
            }
            return Response(response, status=status.HTTP_200_OK)

    @action(detail=False, methods=["GET"])
    def get_talhao(self, request):
        if request.user.is_authenticated:
            try:
                qs = Talhao.objects.all()
                serializer = TalhaoSerializer(qs, many=True)
                area_total = Talhao.objects.aggregate(Sum("area_total"))
                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs),
                    "Area Total dos Talhoes": area_total,
                    "dados": serializer.data,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- --------------------- END TALHAO API --------------------- --------------------- #

    # --------------------- --------------------- START PROJETOS API --------------------- --------------------- #

    @action(detail=False, methods=["GET"])
    def get_projetos(self, request):
        if request.user.is_authenticated:
            try:
                qs = Projeto.objects.values(
                    "nome",
                    "id_d",
                    "fazenda__nome",
                    "fazenda__id_d",
                )

                resumo = {}
                for i in qs:
                    resumo[i["fazenda__nome"]] = {}
                for i in qs:
                    resumo[i["fazenda__nome"]].update({i["id_d"]: i["nome"]})

                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "dados": resumo,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


# --------------------- --------------------- END PROJETOS API --------------------- --------------------- #


class PlantioViewSet(viewsets.ModelViewSet):
    queryset = Plantio.objects.all().order_by("data_plantio")
    serializer_class = PlantioSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    # --------------------- --------------------- PLANTIO API --------------------- --------------------- #

    @action(detail=True, methods=["POST"])
    def save_load_data(self, request, pk=None):
        if request.user.is_authenticated:
            print(request.data)
            if "plantio_arroz" in request.data:
                try:
                    file = request.FILES["plantio_arroz"]
                    entradas = openpyxl.load_workbook(file, data_only=True)
                    worksheet = entradas["Plantio"]
                    plantios = []

                    # DB CONSULT
                    talhao_list = Talhao.objects.all()
                    variedade_list = Variedade.objects.all()
                    safra = Safra.objects.all()[0]
                    ciclo = Ciclo.objects.all()[2]

                    for col in worksheet.iter_rows(min_row=1, max_col=14, max_row=3000):
                        if col[1].value != None and col[0].value != "ID":
                            id_talhao = col[0].value
                            finalizado = True if col[2].value == "Sim" else False
                            (
                                area_colher,
                                data_plantio,
                                dap,
                                id_variedade,
                            ) = (
                                col[8].value,
                                col[10].value,
                                col[11].value,
                                col[12].value,
                            )

                            if id_talhao:
                                try:
                                    talhao_id = [
                                        x
                                        for x in talhao_list
                                        if x.id_unico == id_talhao
                                    ][0]
                                except Exception as e:
                                    print(f"id sem cadastro: {id_talhao}")
                            else:
                                talhao_id = 0
                            try:
                                variedade_id = [
                                    x for x in variedade_list if x.id == id_variedade
                                ][0]
                            except Exception as e:
                                print(f"variedade sem cadastro: {id_variedade}")

                            try:
                                novo_plantio = Plantio(
                                    safra=safra,
                                    ciclo=ciclo,
                                    talhao=talhao_id,
                                    variedade=variedade_id,
                                    area_colheita=area_colher,
                                    data_plantio=data_plantio,
                                )

                                novo_plantio.save()
                            except Exception as e:
                                print(f"Problema em salvar o plantio: {id_variedade}")
                    qs_plantio = Plantio.objects.all()
                    total_plantado = Plantio.objects.aggregate(Sum("area_colheita"))
                    serializer_plantio = PlantioSerializer(qs_plantio, many=True)
                    response = {
                        "msg": f"Consulta realizada com sucesso!!",
                        "total_return": len(qs_plantio),
                        "Area Total dos Talhoes Plantados": total_plantado,
                        "dados": serializer_plantio.data,
                    }
                    return Response(response, status=status.HTTP_200_OK)
                except Exception as e:
                    response = {"message": f"Ocorreu um Erro: {e}"}
                    return Response(response, status=status.HTTP_400_BAD_REQUEST)
            else:
                response = {"message": "Arquivo desconhecido"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API --------------------- ----------------------#
    @action(detail=True, methods=["GET"])
    def get_plantio_from_farmBox(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                # file = request.FILES["plantio_arroz"]
                # file_ = open(os.path.join(settings.BASE_DIR, 'filename'))
                date_file = "2023-05-01"
                with open(f"static/files/dataset-{date_file}.json") as user_file:
                    file_contents = user_file.read()
                    parsed_json = json.loads(file_contents)
                    new_list = parsed_json
                # DB CONSULT
                talhao_list = Talhao.objects.all()
                variedade_list = Variedade.objects.all()
                safra = Safra.objects.all()[1]
                ciclo_list = Ciclo.objects.all()
                projetos = Projeto.objects.all()

                area_total_1 = 0
                area_total_2 = 0
                area_total_3 = 0
                cultura_list = []
                ciclo_and_cultura = []
                ciclo_1 = {}
                ciclo_2 = {}
                ciclo_3 = {}

                for i in new_list:
                    state = i["state"]
                    date_plantio = i["date"]
                    activation_date = ["activation_date"]
                    parcela = i["name"].replace(" ", "")
                    farm_name = i["farm_name"]
                    variedade_name = i["variety_name"]
                    area = i["area"]

                    variedade_planejada = i["planned_variety_name"]
                    cultura_planejada = i["planned_culture_name"]

                    culture_id = i["culture_id"]
                    variety_id = i["variety_id"]
                    fazenda_id = i["farm"]["id"]
                    variedade_planejada_id = i["planned_variety_id"]
                    cultura_planejada_id = i["planned_culture_id"]

                    safra_farm = i["harvest_name"]
                    ciclo_json = i["cycle"]

                    ciclo = ciclo_list[ciclo_json - 1]

                    id_talhao = [
                        x.id_d for x in projetos if x.id_farmbox == fazenda_id
                    ][0]
                    id_variedade = [
                        x
                        for x in variedade_list
                        if x.id_farmbox == variedade_planejada_id
                    ][0]

                    if id_talhao:
                        try:
                            talhao_id = f"{id_talhao}{parcela}"
                            talhao_id = [
                                x for x in talhao_list if x.id_unico == talhao_id
                            ][0]
                        except Exception as e:
                            print(
                                f"{Fore.RED}id sem cadastro: {id_talhao}{parcela} - {farm_name} - Ciclo: {ciclo}{Style.RESET_ALL}"
                            )
                    else:
                        talhao_id = 0
                    try:
                        id_variedade = [
                            x
                            for x in variedade_list
                            if x.id_farmbox == variedade_planejada_id
                        ][0]
                    except Exception as e:
                        print(
                            f"{Fore.RED}variedade sem cadastro: {id_variedade}{Style.RESET_ALL}"
                        )
                    if cultura_planejada:
                        if ciclo_json == 1:
                            if ciclo_1.get(cultura_planejada):
                                area_total = ciclo_1.get(cultura_planejada) + area
                                ciclo_1.update({cultura_planejada: round(area_total)})
                            else:
                                ciclo_1.update({cultura_planejada: round(area)})
                        if ciclo_json == 2:
                            if ciclo_2.get(cultura_planejada):
                                area_total = ciclo_2.get(cultura_planejada) + area
                                ciclo_2.update({cultura_planejada: round(area_total)})
                            else:
                                ciclo_2.update({cultura_planejada: round(area)})
                        if ciclo_json == 3:
                            if ciclo_3.get(cultura_planejada):
                                area_total = ciclo_3.get(cultura_planejada) + area
                                ciclo_3.update({cultura_planejada: round(area_total)})
                            else:
                                ciclo_3.update({cultura_planejada: round(area)})
                print(f"Area Total da Soja Ciclo 1: {area_total_1}")
                print(f"Area Total da Soja Ciclo 2: {area_total_2}")
                print(f"Area Total da Soja Ciclo 3: {area_total_3}")

                print(set(cultura_list))
                print("Ciclo 1")
                for k, v in ciclo_1.items():
                    print(f"Cultura: {k} - Area: {v}")
                print("Ciclo 2")
                for k, v in ciclo_2.items():
                    print(f"Cultura: {k} - Area: {v}")
                print("Ciclo 3")
                for k, v in ciclo_3.items():
                    print(f"Cultura: {k} - Area: {v}")
                qs_plantio = Plantio.objects.filter(safra__safra="2023/2024")

                total_plantado = Plantio.objects.filter(
                    safra__safra="2023/2024", ciclo__ciclo="1"
                ).aggregate(Sum("area_colheita"))

                serializer_plantio = PlantioSerializer(qs_plantio, many=True)
                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs_plantio),
                    "Area Total dos Talhoes Plantados": total_plantado,
                    "dados": serializer_plantio.data,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API --------------------- ----------------------#

    @action(detail=True, methods=["POST"])
    def save_plantio_from_farmBox_json(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                # file = request.FILES["plantio_arroz"]
                # file_ = open(os.path.join(settings.BASE_DIR, 'filename'))
                date_file = "2023-08-11 17:31"
                with open(f"static/files/dataset-{date_file}.json") as user_file:
                    file_contents = user_file.read()
                    parsed_json = json.loads(file_contents)
                    new_list = parsed_json
                # DB CONSULT
                talhao_list = Talhao.objects.all()
                variedade_list = Variedade.objects.all()
                safra = Safra.objects.all()[1]
                ciclo_list = Ciclo.objects.all()
                projetos = Projeto.objects.all()

                area_total_1 = 0
                area_total_2 = 0
                area_total_3 = 0
                cultura_list = []
                ciclo_and_cultura = []
                ciclo_1 = {}
                ciclo_2 = {}
                ciclo_3 = {}

                for i in new_list:
                    state = i["state"]
                    date_plantio = i["date"]
                    activation_date = ["activation_date"]
                    parcela = i["name"].replace(" ", "")
                    farm_name = i["farm_name"]
                    variedade_name = i["variety_name"]
                    area = i["area"]

                    variedade_planejada = i["planned_variety_name"]
                    cultura_planejada = i["planned_culture_name"]

                    culture_id = i["culture_id"]
                    variety_id = i["variety_id"]
                    fazenda_id = i["farm"]["id"]
                    variedade_planejada_id = i["planned_variety_id"]
                    cultura_planejada_id = i["planned_culture_id"]

                    map_centro_id_farm = i["centroid"]
                    map_geo_points_farm = i["geo_points"]

                    safra_farm = i["harvest_name"]
                    ciclo_json = i["cycle"]

                    ciclo = ciclo_list[ciclo_json - 1]

                    id_talhao = [
                        x.id_d for x in projetos if x.id_farmbox == fazenda_id
                    ][0]
                    id_variedade = [
                        x
                        for x in variedade_list
                        if x.id_farmbox == variedade_planejada_id
                    ][0]

                    if id_talhao:
                        try:
                            talhao_id = f"{id_talhao}{parcela}"
                            talhao_id = [
                                x for x in talhao_list if x.id_unico == talhao_id
                            ][0]
                        except Exception as e:
                            print(f"id sem cadastro: {id_talhao}{parcela}")
                    else:
                        talhao_id = 0
                    try:
                        # variedade_id = [
                        #     x for x in variedade_list if x.id == id_variedade
                        # ][0]
                        id_variedade = [
                            x
                            for x in variedade_list
                            if x.id_farmbox == variedade_planejada_id
                        ][0]
                    except Exception as e:
                        print(
                            f"{Fore.RED}variedade sem cadastro: {id_variedade}{Style.RESET_ALL}"
                        )
                    if cultura_planejada:
                        try:
                            novo_plantio = Plantio(
                                safra=safra,
                                ciclo=ciclo,
                                talhao=talhao_id,
                                variedade=id_variedade,
                                area_colheita=area,
                                map_centro_id=map_centro_id_farm,
                                map_geo_points=map_geo_points_farm
                                # data_plantio=data_plantio,
                            )

                            novo_plantio.save()
                            print(
                                f"{Fore.GREEN}Novo Plantio salvo com sucesso: {novo_plantio}{Style.RESET_ALL}"
                            )
                            # print(
                            #     f"{Fore.GREEN}Safra/Ciclo: {safra}-{ciclo} - Estado: {state} - Data Plantio: {date_plantio} - Parcela: {parcela} {Style.RESET_ALL}- Fazenda: {farm_name} - Cultura Planejada: {cultura_planejada} Variedade Planejada: {variedade_planejada}|{id_variedade} - Area: {area} - Cultura_ID: {culture_id} - Variedade_planejada_id: {variedade_planejada_id} - Fazenda_ID: {fazenda_id}"
                            # )
                            # print(
                            #     f"{Fore.YELLOW}Safra:{safra}-Ciclo:{ciclo} - Parcela: {talhao_id} - Variedade: {id_variedade} - area: {area}{Style.RESET_ALL}"
                            # )
                            print("\n")
                        except Exception as e:
                            print(
                                f"{Fore.RED}Problema em salvar o plantio: {id_variedade}{Style.RESET_ALL}{e}"
                            )
                        if ciclo_json == 1:
                            if ciclo_1.get(cultura_planejada):
                                area_total = ciclo_1.get(cultura_planejada) + area
                                ciclo_1.update({cultura_planejada: round(area_total)})
                            else:
                                ciclo_1.update({cultura_planejada: round(area)})
                        if ciclo_json == 2:
                            if ciclo_2.get(cultura_planejada):
                                area_total = ciclo_2.get(cultura_planejada) + area
                                ciclo_2.update({cultura_planejada: round(area_total)})
                            else:
                                ciclo_2.update({cultura_planejada: round(area)})
                        if ciclo_json == 3:
                            if ciclo_3.get(cultura_planejada):
                                area_total = ciclo_3.get(cultura_planejada) + area
                                ciclo_3.update({cultura_planejada: round(area_total)})
                            else:
                                ciclo_3.update({cultura_planejada: round(area)})

                print(f"Area Total da Soja Ciclo 1: {area_total_1}")
                print(f"Area Total da Soja Ciclo 2: {area_total_2}")
                print(f"Area Total da Soja Ciclo 3: {area_total_3}")

                print(set(cultura_list))
                print("Ciclo 1")
                for k, v in ciclo_1.items():
                    print(f"Cultura: {k} - Area: {v}")
                print("Ciclo 2")
                for k, v in ciclo_2.items():
                    print(f"Cultura: {k} - Area: {v}")
                print("Ciclo 3")
                for k, v in ciclo_3.items():
                    print(f"Cultura: {k} - Area: {v}")
                qs_plantio = Plantio.objects.filter(safra__safra="2023/2024")
                total_plantado = Plantio.objects.filter(
                    safra__safra="2023/2024"
                ).aggregate(Sum("area_colheita"))
                serializer_plantio = PlantioSerializer(qs_plantio, many=True)
                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs_plantio),
                    "Area Total dos Talhoes Plantados": total_plantado,
                    "dados": serializer_plantio.data,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API FROM FARMBOX START --------------------- ----------------------#
    @action(detail=True, methods=["GET"])
    def update_plantio_from_farmBox(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                date_file = request.data["filename"]
                print(date_file)
                # file = request.FILES["plantio_arroz"]
                # file_ = open(os.path.join(settings.BASE_DIR, 'filename'))
                # date_file = "2023-09-02 07:41"
                with open(f"static/files/dataset-{date_file}.json") as user_file:
                    file_contents = user_file.read()
                    parsed_json = json.loads(file_contents)
                    new_list = parsed_json
                # DB CONSULT
                talhao_list = Talhao.objects.all()
                variedade_list = Variedade.objects.all()
                safra_list = Safra.objects.all()
                safra_list = [s for s in safra_list]
                ciclo_list = Ciclo.objects.all()
                projetos = Projeto.objects.all()

                count_total = 0
                for i in new_list:
                    state = i["state"]
                    date_plantio = i["date"]
                    emergence_date = i["emergence_date"]
                    activation_date = ["activation_date"]
                    parcela = i["name"].replace(" ", "")
                    farm_name = i["farm_name"]
                    variedade_name = i["variety_name"]
                    area = i["area"]
                    id_plantio_farmbox = i["id"]

                    variedade_planejada = i["planned_variety_name"]
                    cultura_planejada = i["planned_culture_name"]

                    culture_id = i["culture_id"]
                    variety_id = i["variety_id"]
                    fazenda_id = i["farm"]["id"]
                    variedade_planejada_id = i["planned_variety_id"]
                    cultura_planejada_id = i["planned_culture_id"]

                    map_centro_id_farm = i["centroid"]
                    map_geo_points_farm = i["geo_points"]

                    safra_farm = i["harvest_name"]
                    ciclo_json = i["cycle"]

                    ciclo = ciclo_list[ciclo_json - 1]
                    safra = [s for s in safra_list if s.safra == safra_farm][0]

                    id_talhao = [
                        x.id_d for x in projetos if x.id_farmbox == fazenda_id
                    ][0]

                    id_variedade = [
                        x
                        for x in variedade_list
                        if x.id_farmbox == variedade_planejada_id
                    ][0]

                    if id_talhao:
                        try:
                            talhao_id = f"{id_talhao}{parcela}"
                            talhao_id = [
                                x for x in talhao_list if x.id_unico == talhao_id
                            ][0]
                        except Exception as e:
                            print(
                                f"{Fore.RED}id sem cadastro: {id_talhao}{parcela} - {farm_name} - Ciclo: {ciclo}{Style.RESET_ALL}"
                            )
                    else:
                        talhao_id = 0
                    try:
                        id_variedade = [
                            x
                            for x in variedade_list
                            if x.id_farmbox == variedade_planejada_id
                        ][0]
                    except Exception as e:
                        print(
                            f"{Fore.RED}variedade sem cadastro: {id_variedade}{Style.RESET_ALL}"
                        )
                    if cultura_planejada or variety_id:
                        try:
                            field_to_update = Plantio.objects.filter(
                                safra=safra, ciclo=ciclo, talhao=talhao_id
                            )[0]
                            field_to_update.id_farmbox = id_plantio_farmbox
                            if field_to_update.finalizado_colheita == False:
                                if area:
                                    field_to_update.area_colheita = area

                                if map_centro_id_farm:
                                    field_to_update.map_centro_id = map_centro_id_farm

                                if map_geo_points_farm:
                                    field_to_update.map_geo_points = map_geo_points_farm

                                if state == "active":
                                    if date_plantio:
                                        field_to_update.data_plantio = date_plantio
                                        field_to_update.finalizado_plantio = True
                                        field_to_update.area_colheita = area

                                    if emergence_date:
                                        field_to_update.data_emergencia = emergence_date

                                if variety_id:
                                    id_variedade_done = [
                                        x
                                        for x in variedade_list
                                        if x.id_farmbox == variety_id
                                    ][0]
                                    field_to_update.variedade = id_variedade_done
                                else:
                                    field_to_update.variedade = id_variedade
                                field_to_update.save()
                                print(
                                    f"{Fore.GREEN}Plantio Alterado com sucesso: {field_to_update} - {safra} - {ciclo} | {Fore.CYAN}{field_to_update.variedade} | {field_to_update.programa}{Style.RESET_ALL}"
                                )
                                print("\n")
                                count_total += 1
                        except Exception as e:
                            print(
                                f"{Fore.RED}Problema em salvar o plantio: {talhao_id} - {safra} - {ciclo}{Style.RESET_ALL}{e}"
                            )
                    else:
                        try:
                            field_to_update = Plantio.objects.filter(
                                safra=safra, ciclo=ciclo, talhao=talhao_id
                            )[0]
                            if area:
                                field_to_update.area_colheita = area
                            if map_centro_id_farm:
                                field_to_update.map_centro_id = map_centro_id_farm
                            if map_geo_points_farm:
                                field_to_update.map_geo_points = map_geo_points_farm
                            field_to_update.variedade = None
                            field_to_update.programa = None
                            field_to_update.id_farmbox = id_plantio_farmbox

                            field_to_update.save()
                            print(
                                f"{Fore.YELLOW}Plantio Alterado com sucesso para SEM VARIEDADE: {field_to_update}- {safra} - {ciclo}{Style.RESET_ALL}"
                            )
                            print("\n")
                            count_total += 1
                        except Exception as e:
                            print(
                                f"{Fore.RED}Problema em salvar o plantio Não Planejado: {talhao_id} - {safra} - {ciclo}{Style.RESET_ALL}{e}"
                            )

                qs_plantio = Plantio.objects.filter(safra__safra="2023/2024")

                serializer_plantio = PlantioSerializer(qs_plantio, many=True)
                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs_plantio),
                    "Total de Talhões alterados": count_total,
                    "dados": serializer_plantio.data,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
            else:
                response = {"message": "Arquivo desconhecido"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API FROM FARMBOX END--------------------- ----------------------#

    # --------------------- ---------------------- UPDATE GEO POINNTS API FROM FARMBOX START --------------------- ----------------------#
    @action(detail=True, methods=["GET"])
    def update_geopoints(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                date_file = "2023-06-18 11:22- 2023-2024-geral-geo"
                with open(f"static/files/dataset-{date_file}.json") as user_file:
                    file_contents = user_file.read()
                    parsed_json = json.loads(file_contents)
                    new_list = parsed_json
                # DB CONSULT
                talhao_list = Talhao.objects.all()
                variedade_list = Variedade.objects.all()
                safra_list = Safra.objects.all()
                safra_list = [s for s in safra_list]
                ciclo_list = Ciclo.objects.all()
                projetos = Projeto.objects.all()

                count_total = 0
                for i in new_list:
                    state = i["state"]
                    date_plantio = i["date"]
                    emergence_date = i["emergence_date"]
                    activation_date = ["activation_date"]
                    parcela = i["name"].replace(" ", "")
                    farm_name = i["farm_name"]
                    variedade_name = i["variety_name"]
                    area = i["area"]

                    variedade_planejada = i["planned_variety_name"]
                    cultura_planejada = i["planned_culture_name"]

                    culture_id = i["culture_id"]
                    variety_id = i["variety_id"]
                    fazenda_id = i["farm"]["id"]
                    variedade_planejada_id = i["planned_variety_id"]
                    cultura_planejada_id = i["planned_culture_id"]

                    map_centro_id_farm = i["centroid"]
                    map_geo_points_farm = i["geo_points"]

                    safra_farm = i["harvest_name"]
                    ciclo_json = i["cycle"]

                    ciclo = ciclo_list[ciclo_json - 1]
                    safra = [s for s in safra_list if s.safra == safra_farm][0]

                    id_talhao = [
                        x.id_d for x in projetos if x.id_farmbox == fazenda_id
                    ][0]
                    id_variedade = [
                        x
                        for x in variedade_list
                        if x.id_farmbox == variedade_planejada_id
                    ][0]

                    if id_talhao:
                        try:
                            talhao_id = f"{id_talhao}{parcela}"
                            talhao_id = [
                                x for x in talhao_list if x.id_unico == talhao_id
                            ][0]
                        except Exception as e:
                            print(
                                f"{Fore.RED}id sem cadastro: {id_talhao}{parcela} - {farm_name} - Ciclo: {ciclo}{Style.RESET_ALL}"
                            )
                    else:
                        talhao_id = 0
                    try:
                        id_variedade = [
                            x
                            for x in variedade_list
                            if x.id_farmbox == variedade_planejada_id
                        ][0]
                    except Exception as e:
                        print(
                            f"{Fore.RED}variedade sem cadastro: {id_variedade}{Style.RESET_ALL}"
                        )
                    if cultura_planejada or variety_id:
                        try:
                            field_to_update = Plantio.objects.filter(
                                safra=safra, ciclo=ciclo, talhao=talhao_id
                            )[0]
                            if map_centro_id_farm:
                                field_to_update.map_centro_id = map_centro_id_farm

                            if map_geo_points_farm:
                                field_to_update.map_geo_points = map_geo_points_farm

                            field_to_update.save()
                            print(
                                f"{Fore.GREEN}Plantio Alterado com sucesso: {field_to_update}{Style.RESET_ALL}"
                            )
                            print("\n")
                            count_total += 1
                        except Exception as e:
                            print(
                                f"{Fore.RED}Problema em salvar o plantio: {talhao_id} - {safra} - {ciclo}{Style.RESET_ALL}{e}"
                            )

                qs_plantio = Plantio.objects.filter(safra__safra="2023/2024")

                serializer_plantio = PlantioSerializer(qs_plantio, many=True)
                response = {
                    "msg": f"Atualização de Área realizada com sucesso!!",
                    "total_return": len(qs_plantio),
                    "Total de Talhões alterados": count_total,
                    "dados": serializer_plantio.data,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API FROM FARMBOX END--------------------- ----------------------#

    @action(detail=True, methods=["GET"])
    def get_plantio_info(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                qs_plantio_date = Plantio.objects.filter(
                    safra__safra="2023/2024", ciclo="3"
                )
                data_plantada = {}
                area_total = 0
                for i in qs_plantio_date:
                    area_total += i.area_colheita
                    data_plantada.update({i.variedade.cultura.cultura: area_total})

                total_plantado = Plantio.objects.filter(
                    safra__safra="2023/2024", ciclo="3"
                ).aggregate(Sum("area_colheita"))

                serializer_plantio = PlantioSerializer(qs_plantio_date, many=True)
                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs_plantio_date),
                    "Area Total dos Talhoes Plantados": total_plantado,
                    "data_plantada": data_plantada,
                    "dados": serializer_plantio.data,
                }
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API --------------------- ----------------------#

    @action(detail=False, methods=["GET", "POST"])
    def get_plantio(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = None
                cicle_filter = None
                try:
                    safra_filter = request.data["safra"]
                    cicle_filter = request.data["ciclo"]
                except Exception as e:
                    print(e)

                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "2" if cicle_filter == None else cicle_filter

                qs = (
                    Plantio.objects.values(
                        "safra__safra",
                        "pk",
                        "ciclo__ciclo",
                        "talhao__id_talhao",
                        "talhao__fazenda__nome",
                        "talhao__fazenda__fazenda__nome",
                        "variedade__cultura__cultura",
                        "variedade__nome_fantasia",
                        "finalizado_plantio",
                        "finalizado_colheita",
                        "area_colheita",
                        "area_parcial",
                        "data_plantio",
                    )
                    .order_by("talhao__fazenda__nome", "talhao__id_talhao")
                    .filter(
                        safra__safra=safra_filter,
                        ciclo__ciclo=cicle_filter,
                        finalizado_plantio=True,
                    )
                    # .filter(~Q(data_plantio=None))
                )

                qs_annotate = Plantio.objects.filter(
                    safra__safra=safra_filter,
                    ciclo__ciclo=cicle_filter,
                    finalizado_plantio=True,
                )
                res1 = (
                    qs_annotate.values(
                        "talhao__fazenda__nome", "variedade__cultura__cultura"
                    )
                    .order_by("talhao__fazenda__nome")
                    .annotate(area_total=Sum("area_colheita"))
                )
                res2 = (
                    qs_annotate.values(
                        "talhao__fazenda__nome", "talhao__fazenda__fazenda__nome"
                    )
                    .annotate(count=Count("talhao__fazenda__nome"))
                    .order_by("talhao__fazenda__nome")
                )

                # ------------- ------------- START SEPARADO POR PROJETO ------------- -------------#
                resumo = {i["talhao__fazenda__nome"]: {} for i in qs}

                {
                    resumo[i["talhao__fazenda__nome"]].update(
                        {
                            i["talhao__id_talhao"]: {
                                "safra": i["safra__safra"],
                                "ciclo": i["ciclo__ciclo"],
                                "cultura": i["variedade__cultura__cultura"],
                                "variedade": i["variedade__nome_fantasia"],
                                "finalizado_colheita": i["finalizado_colheita"],
                                "id_plantio": i["pk"],
                            }
                        }
                    )
                    for i in qs
                }
                # ------------- ------------- END SEPARADO POR PROJETO ------------- -------------#

                # ------------- ------------- START SEPARADO POR FAZENDA > PROJETO ------------- -------------#
                # resumo = {}
                # for i in qs:
                #     resumo[i["talhao__fazenda__fazenda__nome"]] = {
                #         i["talhao__fazenda__nome"]: {}
                #     }

                # for i in qs:
                #     resumo[i["talhao__fazenda__fazenda__nome"]].update(
                #         {i["talhao__fazenda__nome"]: {}}
                #     )
                # for i in qs:
                #     resumo[i["talhao__fazenda__fazenda__nome"]][
                #         i["talhao__fazenda__nome"]
                #     ].update(
                #         {
                #             i["talhao__id_talhao"]: {
                #                 "safra": i["safra__safra"],
                #                 "ciclo": i["ciclo__ciclo"],
                #                 "cultura": i["variedade__cultura__cultura"],
                #                 "variedade": i["variedade__nome_fantasia"],
                #                 "finalizado_colheita": i["finalizado_colheita"],
                #             }
                #         }
                #     )

                # ------------- ------------- END SEPARADO POR FAZENDA > PROJETO ------------- -------------#

                area_total = qs_annotate.aggregate(Sum("area_colheita"))

                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs),
                    "resumo_safra": res1,
                    "resumo_safra_fazenda": res2,
                    "Area Total dos Talhoes Plantados": area_total,
                    "dados": resumo,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- --------------------- END PLANTIO API --------------------- --------------------- #

    # --------------------- --------------------- START PLANTIO API DONE --------------------- --------------------- #

    @action(detail=False, methods=["GET", "POST"])
    def get_plantio_done(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = request.data["safra"]
                cicle_filter = request.data["ciclo"]

                print(safra_filter)
                print(cicle_filter)
                # safra_filter = request.POST.get("safra")
                # cicle_filter = request.POST.get("ciclo")
                # print(safra_from_request, ciclo_from_request)
                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "1" if cicle_filter == None else cicle_filter

                qs = (
                    Plantio.objects.values(
                        "safra__safra",
                        "ciclo__ciclo",
                        "talhao__id_talhao",
                        "talhao__id_unico",
                        "talhao__fazenda__nome",
                        "talhao__fazenda__map_centro_id",
                        "talhao__fazenda__fazenda__nome",
                        "variedade__cultura__cultura",
                        "variedade__dias_ciclo",
                        "variedade__cultura__map_color",
                        "variedade__cultura__map_color_line",
                        "variedade__nome_fantasia",
                        "variedade__variedade",
                        "area_colheita",
                        "data_plantio",
                        "map_centro_id",
                        "map_geo_points",
                        "cronograma_programa__0",
                        "finalizado_plantio",
                        "finalizado_colheita",
                        "plantio_descontinuado",
                    )
                    .order_by(
                        "data_plantio", "talhao__fazenda__nome", "talhao__id_talhao"
                    )
                    .filter(safra__safra=safra_filter, ciclo__ciclo=cicle_filter)
                    # .filter(finalizado_plantio=True)
                    .filter(plantio_descontinuado=False)
                )

                qs_by_day = (
                    Plantio.objects.values(
                        "data_plantio",
                        "talhao__fazenda__nome",
                        "talhao__fazenda__fazenda__nome",
                        "variedade__cultura__cultura",
                    )
                    .annotate(area_total=Sum("area_colheita"))
                    .filter(finalizado_plantio=True, plantio_descontinuado=False)
                    .filter(safra__safra=safra_filter, ciclo__ciclo=cicle_filter)
                    .order_by("data_plantio")
                )

                response = {
                    "msg": f"Consulta realizada com sucesso GetPlantioDone API!! - Safra: {safra_filter} - Ciclo: {cicle_filter}",
                    "total_return": len(qs),
                    "data": qs,
                    "plantio_by_day": qs_by_day
                    # "resume_by_farm": qsFarm,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- --------------------- END PLANTIO API DONE --------------------- --------------------- #

    @action(detail=True, methods=["POST"])
    def update_plantio_data(self, request, pk=None):
        if request.user.is_authenticated:
            print(request.data)
            if "plantio_arroz" in request.data:
                try:
                    file = request.FILES["plantio_arroz"]
                    entradas = openpyxl.load_workbook(file, data_only=True)
                    worksheet = entradas["Plantio"]
                    plantios = []

                    # DB CONSULT
                    talhao_list = Talhao.objects.all()
                    variedade_list = Variedade.objects.all()
                    safra_2022_2023 = 0
                    safra = Safra.objects.all()[safra_2022_2023]
                    ciclo_1 = 0
                    ciclo_2 = 1
                    ciclo_3 = 2
                    ciclo = Ciclo.objects.all()[ciclo_3]

                    for col in worksheet.iter_rows(min_row=1, max_col=14, max_row=3000):
                        if col[1].value != None and col[0].value != "ID":
                            id_talhao = col[0].value
                            finalizado = True if col[2].value == "Sim" else False
                            (
                                area_colher,
                                data_plantio,
                                dap,
                                id_variedade,
                            ) = (
                                col[8].value,
                                col[10].value,
                                col[11].value,
                                col[13].value,
                            )

                            if id_talhao:
                                try:
                                    talhao_id = [
                                        x
                                        for x in talhao_list
                                        if x.id_unico == id_talhao
                                    ][0]
                                except Exception as e:
                                    print(f"id sem cadastro: {id_talhao}")
                            else:
                                talhao_id = 0
                            try:
                                variedade_id = [
                                    x for x in variedade_list if x.id == id_variedade
                                ][0]
                                print(
                                    safra,
                                    ciclo,
                                    talhao_id,
                                    talhao_id.id_unico,
                                    variedade_id,
                                    area_colher,
                                    data_plantio,
                                    finalizado,
                                    dap,
                                )
                            except Exception as e:
                                print(f"variedade sem cadastro: {id_variedade}")
                            try:
                                Plantio.objects.filter(
                                    talhao__id_unico=talhao_id.id_unico,
                                    safra=safra,
                                    ciclo=ciclo,
                                ).update(finalizado_colheita=finalizado)

                            except Exception as e:
                                print(
                                    f"Problema em Atualiar o plantio: {talhao_id} - {e}"
                                )

                    qs_plantio_finalizado = Plantio.objects.filter(
                        finalizado_colheita=True
                    )
                    total_plantado = Plantio.objects.aggregate(Sum("area_colheita"))

                    total_plantado_finalizado = Plantio.objects.filter(
                        finalizado_colheita=True
                    ).aggregate(Sum("area_colheita"))

                    qs_plantio = Plantio.objects.all()
                    serializer_plantio = PlantioSerializer(qs_plantio, many=True)

                    response = {
                        "msg": f"Parcelas Atualizadas com successo!!",
                        "total_return": len(qs_plantio),
                        "Area Total dos Talhoes Plantados": total_plantado,
                        "Area Total dos Talhoes Plantados Finalizados": total_plantado_finalizado,
                        "Quantidade Total de Parcelas Finalizadas": len(
                            qs_plantio_finalizado
                        ),
                        "dados": serializer_plantio.data,
                    }

                    return Response(response, status=status.HTTP_200_OK)
                except Exception as e:
                    response = {"message": f"Ocorreu um Erro: {e}"}
                    return Response(response, status=status.HTTP_400_BAD_REQUEST)
            else:
                response = {"message": "Arquivo desconhecido"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # Plantio.objects.filter(talhao__id_unico="7B13").update(veiculos_carregados=4)

    # --------------------- ---------------------- UPDATE PLANTIO API --------------------- ----------------------#
    @action(detail=False, methods=["GET"])
    def get_plantio_cronograma_programa(self, request):
        if request.user.is_authenticated:
            try:
                farmer_filter_id = 11
                projeto = Projeto.objects.filter(id=farmer_filter_id)[0].nome

                qs = Plantio.objects.values(
                    "id",
                    "talhao__id_talhao",
                    "talhao_id",
                    "talhao__fazenda__nome",
                    "variedade__nome_fantasia",
                    "area_colheita",
                    "data_plantio",
                    # "get_cronograma_programa",
                ).filter(programa_id=6)
                ids_list = qs.values("id")

                qs_filtered = Plantio.objects.filter(id__in=ids_list)

                crono_list = [
                    (x.get_cronograma_programa, x.get_dap) for x in qs_filtered
                ]

                print(crono_list[0][1])

                final_return = []
                for i in crono_list:
                    dict_up = qs.filter(id=i[0][0]["id"])[0]
                    dict_up.update({"DAP": i[1]})
                    dict_up.update({"cronograma": i[0]})
                    final_return.append(dict_up)

                # final_return = [
                #     {
                #         "parcela": i.talhao.id_talhao,
                #         "data plantio": i.data_plantio,
                #         "area plantio": i.area_colheita,
                #         "cultura": i.variedade.cultura.cultura,
                #         "variedade": i.variedade.variedade,
                #         "Cronograma": i.get_cronograma_programa,
                #     }
                #     for i in Plantio.objects.filter(
                #         safra__safra="2023/2024",
                #         ciclo__ciclo="1",
                #         talhao__fazenda_id=farmer_filter_id,
                #     )
                # ]

                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs),
                    "projeto": projeto,
                    "dados": final_return,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO APLICACOES API START --------------------- ----------------------#

    @action(detail=False, methods=["GET", "POST"])
    def get_plantio_operacoes_detail(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = request.data["safra"]
                cicle_filter = request.data["ciclo"]
                print(safra_filter)
                print(cicle_filter)
                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "1" if cicle_filter == None else cicle_filter
                qs_planejamento = (
                    PlannerPlantio.objects.select_related(
                        "projeto",
                        "cultura",
                        "ciclo",
                        "cultura",
                        "projeto__fazenda",
                        "safra",
                    )
                    .values(
                        "projeto",
                        "projeto__id",
                        "projeto__nome",
                        "cultura",
                        "variedade",
                        "safra__safra",
                        "ciclo__ciclo",
                        "start_date",
                        "area",
                    )
                    .filter(safra__safra=safra_filter, ciclo__ciclo=cicle_filter)
                )
                qs_plantio = (
                    Plantio.objects.select_related(
                        "safra",
                        "ciclo",
                        "talhao",
                        "fazenda",
                        "programa",
                        "variedade",
                        "variedade__cultura",
                        "talhao__fazenda__fazenda",
                    )
                    .values(
                        "id",
                        "talhao__id_talhao",
                        "talhao__id_unico",
                        "talhao_id",
                        "safra__safra",
                        "ciclo__ciclo",
                        "talhao__fazenda__nome",
                        "talhao__fazenda__id",
                        "talhao__fazenda__fazenda__nome",
                        "talhao__fazenda__fazenda__capacidade_plantio_ha_dia",
                        "variedade__nome_fantasia",
                        "variedade__cultura__cultura",
                        "area_colheita",
                        "data_plantio",
                        "finalizado_plantio",
                        "programa",
                        "programa_id",
                        "programa__start_date",
                        "programa__end_date",
                        "programa__nome",
                    )
                    .filter(~Q(programa_id=None))
                    .filter(safra=s_dict[safra_filter], ciclo=c_dict[cicle_filter])
                    .filter(Q(data_plantio=None))
                    .filter(plantio_descontinuado=False)
                )
                qs_programas = Operacao.objects.values(
                    "estagio", "programa_id", "prazo_dap", "id"
                ).filter(ativo=True)
                qs_aplicacoes = (
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
                    .filter(~Q(operacao__programa_id=None))
                    .filter(
                        operacao__programa__safra=s_dict[safra_filter],
                        operacao__programa__ciclo=c_dict[cicle_filter],
                        ativo=True,
                    )
                )

                final_result = {i["talhao__fazenda__nome"]: {} for i in qs_plantio}
                try:
                    {
                        final_result[i["talhao__fazenda__nome"]].update(
                            {
                                i["talhao__id_talhao"]: {
                                    "safra": i["safra__safra"],
                                    "ciclo": i["ciclo__ciclo"],
                                    "cultura": i["variedade__cultura__cultura"],
                                    "variedade": i["variedade__nome_fantasia"],
                                    "plantio_id": i["id"],
                                    "fazenda_grupo": i[
                                        "talhao__fazenda__fazenda__nome"
                                    ],
                                    "projeto_id": i["talhao__fazenda__id"],
                                    "talhao_id_unico": i["talhao__id_unico"],
                                    "plantio_finalizado": i["finalizado_plantio"],
                                    "area_colheita": i["area_colheita"],
                                    "data_plantio": i["data_plantio"],
                                    "dap": get_dap(i["data_plantio"]),
                                    "programa_id": i["programa"],
                                    "programa": i["programa__nome"],
                                    "programa_start_date": i["programa__start_date"],
                                    "programa_end_date": i["programa__end_date"],
                                    "capacidade_plantio_dia": i[
                                        "talhao__fazenda__fazenda__capacidade_plantio_ha_dia"
                                    ],
                                    "cronograma": [
                                        {
                                            "estagio": x["estagio"],
                                            "dap": x["prazo_dap"],
                                            "data prevista": get_prev_app_date(
                                                i["data_plantio"], x["prazo_dap"]
                                            ),
                                            "produtos": [
                                                {
                                                    "produto": y["defensivo__produto"],
                                                    "tipo": y["defensivo__tipo"],
                                                    "dose": y["dose"],
                                                    "quantidade aplicar": get_quantidade_aplicar(
                                                        y["dose"], i["area_colheita"]
                                                    ),
                                                }
                                                for y in qs_aplicacoes
                                                if x["programa_id"] == i["programa"]
                                                and y["operacao"] == x["id"]
                                            ],
                                        }
                                        for x in qs_programas
                                        if x["programa_id"] == i["programa"]
                                    ],
                                }
                            }
                        )
                        for i in qs_plantio
                    }
                except Exception as e:
                    print("erro ao gerar", e)

                prev_date = {}
                # 50 ha por dia
                # max_day = 50

                # PROGRAMA PARA GERAR DATAS FUTURAS DE ACORDO COM A LÓGICA PARA
                for k, v in final_result.items():
                    prev_date.update(
                        {
                            k: {
                                "area": 0,
                                "dias_necessários": 0,
                                "data_inicial": None,
                                "data_final": None,
                            }
                        }
                    )
                    # print("inside loop : ", k)
                    filtered_planner = qs_planejamento.filter(projeto__nome=k)
                    planner_date = False
                    if filtered_planner:
                        # print("aqui temos planejamneto: , ", filtered_planner)
                        current_planner = filtered_planner[0]
                        inital_date_planner = current_planner["start_date"]
                        planner_date = True

                    for kk, vv in v.items():
                        # print("VVV :", vv)
                        # print("\n")
                        projeto_id = vv["projeto_id"]

                        data_plantio = vv["data_plantio"]
                        area_colheita = vv["area_colheita"]
                        start_date = vv["programa_start_date"]
                        end_date = vv["programa_end_date"]
                        cronograma = vv["cronograma"]
                        capacidade_dia = vv["capacidade_plantio_dia"]

                        prev_date[k]["area"] += vv["area_colheita"]
                        prev_date[k]["dias_necessários"] = round(
                            prev_date[k]["area"] / capacidade_dia
                        )
                        if planner_date:
                            prev_date[k]["data_inicial"] = get_base_date(
                                inital_date_planner
                            )
                        else:
                            prev_date[k]["data_inicial"] = get_base_date(start_date)
                        prev_date[k]["data_final"] = prev_date[k][
                            "data_inicial"
                        ] + datetime.timedelta(days=prev_date[k]["dias_necessários"])
                        # ------------HERE is the challenge-------------------#
                        if data_plantio is None:
                            final_result[k][kk].update(
                                {
                                    "data_plantio": prev_date[k]["data_inicial"]
                                    + datetime.timedelta(
                                        days=prev_date[k]["dias_necessários"]
                                    )
                                }
                            )
                        prev_date[k]["dias_necessários"] = round(
                            prev_date[k]["area"] / capacidade_dia
                        )
                        index = 0
                        for vvv in final_result[k][kk]["cronograma"]:
                            final_result[k][kk]["cronograma"][index].update(
                                {
                                    "data prevista": final_result[k][kk]["data_plantio"]
                                    + datetime.timedelta(days=vvv["dap"] - 1),
                                    "aplicado": False,
                                }
                            )
                            index += 1
                print(qs_planejamento)

                # RESUMO POR DIA COM TOTAIS DE APLICACOES
                final_by_day = []

                final = []

                def find_exs(x):
                    if x["data"]:
                        return True
                    else:
                        return False

                for k, v in final_result.items():
                    for kk, vv in v.items():
                        final.append({"fazenda": k, "parcela": kk, "dados": vv})
                        cronograma = vv["cronograma"]
                        for kkk in cronograma:
                            data_prev_cronograma = kkk["data prevista"]
                            produtos_cronograma = kkk["produtos"]
                            exists = [
                                [x["data"], ind]
                                for ind, x in enumerate(final_by_day)
                                if x["data"] == data_prev_cronograma
                            ]
                            if exists:
                                indice_data_existente = exists[0][1]
                                dict_to_update = final_by_day[exists[0][1]]["produtos"]

                                for i in produtos_cronograma:
                                    filtered = [
                                        (index, x["produto"], x["quantidade"])
                                        for index, x in enumerate(
                                            final_by_day[exists[0][1]]["produtos"]
                                        )
                                        if x["produto"] == i["produto"]
                                    ]

                                    # add quantity to product that already exists
                                    if filtered:
                                        index_of = filtered[0][0]
                                        value_of_upda = filtered[0][2]
                                        final_by_day[exists[0][1]]["produtos"][
                                            index_of
                                        ].update(
                                            {
                                                "produto": i["produto"],
                                                "tipo": i["tipo"],
                                                "quantidade": i["quantidade aplicar"]
                                                + value_of_upda,
                                            }
                                        )
                                    else:
                                        dict_to_update.append(
                                            {
                                                "produto": i["produto"],
                                                "tipo": i["tipo"],
                                                "quantidade": i["quantidade aplicar"],
                                            }
                                        )
                            else:
                                final_by_day.append(
                                    {
                                        "data": data_prev_cronograma,
                                        "produtos": [
                                            {
                                                "produto": x["produto"],
                                                "quantidade": x["quantidade aplicar"],
                                            }
                                            for x in produtos_cronograma
                                        ],
                                    }
                                )

                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "prev_date": prev_date,
                    "app_date": final_by_day,
                    "total_query_plantio": qs_plantio.count(),
                    "total_return_plantio": len(final_result),
                    "dados": final,
                    # "dados_plantio": qs_plantio,
                    # "total_return_aplicacoes": len(qs_aplicacoes),
                    # "dados_aplicacoes": qs_aplicacoes,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO APLICACOES API END --------------------- ----------------------#

    @action(detail=False, methods=["GET", "POST"])
    def get_plantio_operacoes_detail_json_program(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = request.data["safra"]
                cicle_filter = request.data["ciclo"]

                print(safra_filter)
                print(cicle_filter)

                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "1" if cicle_filter == None else cicle_filter

                qs_plantio = (
                    Plantio.objects.select_related(
                        "safra",
                        "ciclo",
                        "talhao",
                        "fazenda",
                        "programa",
                        "variedade",
                        "variedade__cultura",
                        "talhao__fazenda",
                        "talhao__fazenda__fazenda",
                    )
                    .values(
                        "id",
                        "talhao__id_talhao",
                        "talhao__id_unico",
                        "talhao_id",
                        "safra__safra",
                        "ciclo__ciclo",
                        "talhao__fazenda__nome",
                        "talhao__fazenda__fazenda__nome",
                        "talhao__fazenda__fazenda__capacidade_plantio_ha_dia",
                        "variedade__nome_fantasia",
                        "variedade__cultura__cultura",
                        "area_colheita",
                        "data_plantio",
                        "finalizado_plantio",
                        "programa",
                        "programa_id",
                        "programa__start_date",
                        "programa__end_date",
                        "programa__nome",
                        "programa__nome_fantasia",
                        "cronograma_programa",
                    )
                    .filter(~Q(programa_id=None))
                    .filter(safra=s_dict[safra_filter], ciclo=c_dict[cicle_filter])
                    .filter(data_plantio__isnull=False)
                    .filter(plantio_descontinuado=False)
                )
                try:
                    result = [
                        {
                            "fazenda": i["talhao__fazenda__nome"],
                            "parcela": i["talhao__id_talhao"],
                            "dados": {
                                "safra": i["safra__safra"],
                                "ciclo": i["ciclo__ciclo"],
                                "cultura": i["variedade__cultura__cultura"],
                                "variedade": i["variedade__nome_fantasia"],
                                "plantio_id": i["id"],
                                "fazenda_grupo": i["talhao__fazenda__fazenda__nome"],
                                "talhao_id_unico": i["talhao__id_unico"],
                                "plantio_finalizado": i["finalizado_plantio"],
                                "area_colheita": i["area_colheita"],
                                "data_plantio": i["data_plantio"],
                                "data_inicio_plantio": i["cronograma_programa"][0][
                                    "Data Plantio"
                                ],
                                "dap": get_dap(
                                    i["cronograma_programa"][0]["Data Plantio"]
                                ),
                                "programa_id": i["programa"],
                                "programa": i["programa__nome"],
                                "programa_start_date": i["programa__start_date"],
                                "programa_end_date": i["programa__end_date"],
                                "capacidade_plantio_dia": i[
                                    "talhao__fazenda__fazenda__capacidade_plantio_ha_dia"
                                ],
                                "cronograma": [
                                    {
                                        **x,
                                        "estagio": x["estagio"]
                                        + "|"
                                        + i["programa__nome_fantasia"],
                                    }
                                    for x in i["cronograma_programa"][1:]
                                ],
                            },
                        }
                        for i in qs_plantio
                    ]
                except Exception as e:
                    print(f"erro ao gerar o cronograma {e}")

                response = {
                    "msg": f"Retorno com os arquivos Json com Sucesso!!",
                    "total_query_plantio": qs_plantio.count(),
                    "dados_plantio": result,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO APLICACOES TESTE JSON FIELD API START --------------------- ----------------------#

    # --------------------- ---------------------- PLANTIO MAP GEO API END --------------------- ----------------------#

    @action(detail=False, methods=["GET", "POST"])
    def get_plantio_detail_map(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = None
                cicle_filter = None
                try:
                    safra_filter = request.data["safra"]
                    cicle_filter = request.data["ciclo"]
                except Exception as e:
                    print(e)
                print(safra_filter)
                print(cicle_filter)
                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "1" if cicle_filter == None else cicle_filter

                qs_plantio = (
                    Plantio.objects.select_related(
                        "safra",
                        "ciclo",
                        "talhao",
                        "fazenda",
                        "programa",
                        "variedade",
                        "variedade__cultura",
                        "talhao__fazenda",
                        "talhao__fazenda__fazenda",
                    )
                    .values(
                        "id",
                        "talhao__id_talhao",
                        "talhao__id_unico",
                        "talhao_id",
                        "safra__safra",
                        "ciclo__ciclo",
                        "talhao__fazenda__nome",
                        "talhao__fazenda__map_centro_id",
                        "talhao__fazenda__map_zoom",
                        "talhao__fazenda__fazenda__nome",
                        "variedade__nome_fantasia",
                        "variedade__cultura__cultura",
                        "variedade__cultura__map_color",
                        "variedade__cultura__map_color_line",
                        "finalizado_plantio",
                        "finalizado_colheita",
                        "plantio_descontinuado",
                        "area_colheita",
                        "map_centro_id",
                        "map_geo_points",
                    )
                    .filter(safra=s_dict[safra_filter], ciclo=c_dict[cicle_filter])
                )

                result = [
                    {
                        "fazenda": i["talhao__fazenda__nome"],
                        "parcela": i["talhao__id_talhao"],
                        "dados": {
                            "safra": i["safra__safra"],
                            "ciclo": i["ciclo__ciclo"],
                            "cultura": i["variedade__cultura__cultura"],
                            "variedade": i["variedade__nome_fantasia"],
                            "plantio_id": i["id"],
                            "finalizado_plantio": i["finalizado_plantio"],
                            "finalizado_colheita": i["finalizado_colheita"],
                            "plantio_descontinuado": i["plantio_descontinuado"],
                            "fazenda_grupo": i["talhao__fazenda__fazenda__nome"],
                            "talhao_id_unico": i["talhao__id_unico"],
                            "area_colheita": i["area_colheita"],
                            "map_geo_points": i["map_geo_points"],
                            "map_geo_points_center": i["map_centro_id"],
                            "variedade_color": i["variedade__cultura__map_color"],
                            "variedade_color_line": i[
                                "variedade__cultura__map_color_line"
                            ],
                            "projeto_map_centro_id": i[
                                "talhao__fazenda__map_centro_id"
                            ],
                            "projeto_map_zoom": i["talhao__fazenda__map_zoom"],
                        },
                    }
                    for i in qs_plantio
                ]

                response = {
                    "msg": f"Retorno com os arquivos DE MAPAS com Sucesso!!",
                    "total_query_plantio": qs_plantio.count(),
                    "dados_plantio": result,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO UPDATE APLICATION FIELD API START --------------------- ----------------------#

    # --------------------- ---------------------- PLANTIO PRODUTIVIDADE MAP API START --------------------- ----------------------#
    @action(detail=False, methods=["GET", "POST"])
    def get_produtividade_plantio(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = None
                cicle_filter = None
                try:
                    safra_filter = request.data["safra"]
                    cicle_filter = request.data["ciclo"]
                except Exception as e:
                    print(e)
                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "1" if cicle_filter == None else cicle_filter
                qs_colheita = Colheita.objects.values(
                    "plantio__id",
                    "plantio__talhao__fazenda__nome",
                    "plantio__talhao__id_talhao",
                    "plantio__area_colheita",
                    "plantio__finalizado_colheita",
                    "plantio__area_parcial",
                ).annotate(
                    peso_kg=Round((Sum("peso_scs_limpo_e_seco") * 60), precision=2),
                    peso_scs=Round(Sum("peso_scs_limpo_e_seco"), precision=2),
                    # produtividade=Round(
                    #     ("peso_scs" / "plantio__area_colheita"),
                    #     precision=2,
                    #     output_field=DecimalField(),
                    # ),
                )
                qs_plantio = Plantio.objects.values(
                    "id",
                    "talhao__id_talhao",
                    "talhao__id_unico",
                    "talhao_id",
                    "safra__safra",
                    "ciclo__ciclo",
                    "talhao__fazenda__nome",
                    "talhao__fazenda__map_centro_id",
                    "talhao__fazenda__map_zoom",
                    "talhao__fazenda__fazenda__nome",
                    "variedade__nome_fantasia",
                    "variedade__cultura__cultura",
                    "variedade__cultura__map_color",
                    "variedade__cultura__map_color_line",
                    "finalizado_plantio",
                    "finalizado_colheita",
                    "area_colheita",
                    "area_parcial",
                    "map_centro_id",
                    "map_geo_points",
                ).filter(
                    safra=s_dict[safra_filter],
                    ciclo=c_dict[cicle_filter],
                    plantio_descontinuado=False,
                )

                result = [x for x in qs_plantio]
                for i in qs_colheita:
                    for j in result:
                        if i["plantio__id"] == j["id"]:
                            j["peso_kg"] = i["peso_kg"]
                            j["peso_scs"] = i["peso_scs"]
                            if i["plantio__finalizado_colheita"] == True:
                                j["produtividade"] = (
                                    i["peso_scs"] / i["plantio__area_colheita"]
                                )
                            else:
                                area_parcial = (
                                    i["plantio__area_parcial"]
                                    if i["plantio__area_parcial"]
                                    else None
                                )
                                j["produtividade"] = (
                                    i["peso_scs"] / area_parcial if area_parcial else 0
                                )

                response = {
                    "msg": f"Retorno com os arquivos DE MAPAS e Produtividades com Sucesso!!",
                    # "total_query_plantio": qs_plantio.count(),
                    # "dados_colheita": qs_colheita,
                    "dados_plantio": result,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO PRODUTIVIDADE MAP API END --------------------- ----------------------#

    @action(detail=False, methods=["GET", "POST", "PUT"])
    def update_aplication_plantio(sef, request, pk=None):
        if request.user.is_authenticated:
            try:
                params = request.data["data"]
                print(params)
                id_list = [x["id"] for x in params]
                print("list of IDS: ", id_list)
                list_updated = []
                for i in params:
                    try:
                        update_field = Plantio.objects.get(pk=i["id"])
                        index = get_index_dict_estagio(
                            update_field.cronograma_programa, i["estagio"]
                        )
                        print(
                            f"{update_field.talhao.fazenda.nome} - {update_field.talhao.id_talhao}"
                        )
                        print(update_field.cronograma_programa[index]["estagio"])
                        print(update_field.cronograma_programa[index]["aplicado"])
                        print("\n")
                        field_to_update = update_field.cronograma_programa[index][
                            "aplicado"
                        ]

                        new_value = None
                        if field_to_update == True:
                            new_value = False

                        if field_to_update == False:
                            new_value = True

                        update_field.cronograma_programa[index]["aplicado"] = new_value
                        update_field.save()

                        updated = {
                            "talhao": update_field.talhao.id_talhao,
                            "estagio": update_field.cronograma_programa[index][
                                "estagio"
                            ],
                            "situação": update_field.cronograma_programa[index][
                                "aplicado"
                            ],
                        }
                        print("updated at: ", updated)
                        list_updated.append(updated)
                    except Exception as e:
                        print("Erro ao atualizar a Ap no DB", e)

                response = {
                    "msg": "Atualização realizada com sucesso!",
                    "data": params,
                    "result": list_updated,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)

        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["GET", "POST"])
    def get_plantio_calendar_done(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                qs = (
                    Plantio.objects.filter(
                        safra__safra="2023/2024",
                        finalizado_plantio=True,
                        plantio_descontinuado=False,
                    )
                    .filter(~Q(variedade__cultura__cultura="Milheto"))
                    .values(
                        "talhao__fazenda__nome",
                        "variedade__cultura__cultura",
                        "variedade__variedade",
                        "ciclo__ciclo",
                    )
                    .annotate(
                        month=ExtractMonth("data_plantio"),
                        year=ExtractYear("data_plantio"),
                        area_total=Sum("area_colheita"),
                    )
                    .order_by("year", "ciclo__ciclo", "month", "talhao__fazenda__nome")
                )
                response = {
                    "msg": "Consulta realizada com sucesso!!",
                    "data": qs,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)

        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO UPDATE APLICATION FIELD API END --------------------- ----------------------#

    # @action(detail=False, methods=["GET"])
    # def get_new_information(self, request, pk=None):
    #     if request.user.is_authenticated:
    #         try:
    #             print("successfull")
    # data = mongo_api.read_data_from_db(db_name)
    #             response = {
    #                 "msg": f"Consulta realizada com sucesso!!",
    #                 "dados": data,
    #             }
    #             return Response(response, status=status.HTTP_200_OK)
    #         except Exception as e:
    #             print("error")
    #             response = f"erro na requisição: {e}"
    #             return Response(response, status=status.HTTP_400_BAD_REQUEST)
    #     else:
    #         response = {"message": "Você precisa estar logado!!!"}
    #         return Response(response, status=status.HTTP_400_BAD_REQUEST)


# --------------------- ---------------------- DEFENSIVOS API START --------------------- ----------------------#


class DefensivoViewSet(viewsets.ModelViewSet):
    queryset = Defensivo.objects.all().order_by("produto")
    serializer_class = DefensivoSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    @action(detail=True, methods=["POST"])
    def save_defensivo_data(self, request, pk=None):
        if request.user.is_authenticated:
            if "defensivos" in request.data:
                try:
                    file = request.FILES["defensivos"]
                    entradas = openpyxl.load_workbook(file, data_only=True)
                    worksheet = entradas["defensivos"]
                    for col in worksheet.iter_rows(min_row=1, max_col=5, max_row=3000):
                        if col[1].value != None and col[0].value != "ID":
                            produto = col[0].value.strip()
                            unidade_medida = col[1].value
                            formulacao = col[2].value
                            tipo = col[3].value

                            try:
                                new_product = Defensivo(
                                    produto=produto,
                                    unidade_medida=unidade_medida,
                                    formulacao=formulacao,
                                    tipo=tipo,
                                )
                                new_product.save()
                                print(
                                    f"Novo Defensivo Salvo com sucesso!! - {new_product.produto}"
                                )
                            except Exception as e:
                                print(f"Erro ao Salvar o produto {produto} - Erro: {e}")
                    qs_defensivos = Defensivo.objects.all()
                    serializer_defensivos = DefensivoSerializer(
                        qs_defensivos, many=True
                    )

                    response = {
                        "msg": f"Defensivos Atualizados com sucesso!!",
                        "total_return": len(qs_defensivos),
                        "dados": serializer_defensivos.data,
                    }
                    return Response(response, status=status.HTTP_200_OK)
                except Exception as e:
                    response = {"message": f"Ocorreu um Erro: {e}"}
                    return Response(response, status=status.HTTP_400_BAD_REQUEST)
            else:
                response = {"message": "Arquivo desconhecido"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


# --------------------- ---------------------- DEFENSIVOS API END  --------------------- ----------------------#


# --------------------- ---------------------- PROGRAMS API START  --------------------- ----------------------#


class ProgramasDetails(viewsets.ModelViewSet):
    queryset = Aplicacao.objects.all()
    serializer_class = AplicacaoSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    @action(detail=False, methods=["GET"])
    def get_operacoes(self, request):
        if request.user.is_authenticated:
            try:
                safra_filter = None
                cicle_filter = None
                try:
                    safra_filter = request.data["safra"]
                    cicle_filter = request.data["ciclo"]
                except Exception as e:
                    print(e)
                print(safra_filter)
                print(cicle_filter)
                safra_filter = "2023/2024" if safra_filter == None else safra_filter
                cicle_filter = "1" if cicle_filter == None else cicle_filter
                qs = Aplicacao.objects.values(
                    "criados",
                    # "modificado",
                    "dose",
                    "obs",
                    "operacao__estagio",
                    "operacao__prazo_dap",
                    "operacao__programa__nome",
                    # "operacao__programa__nome_fantasia",
                    "operacao__programa__cultura__cultura",
                    "operacao__programa__safra__safra",
                    "operacao__programa__ciclo__ciclo",
                    "defensivo__produto",
                    "defensivo__tipo",
                ).filter(
                    Q(ativo=True)
                    & Q(operacao__programa__ativo=True)
                    & Q(operacao__ativo=True)
                )
                qs_estagios = Operacao.objects.values(
                    "estagio", "programa__nome", "prazo_dap", "obs"
                ).filter(Q(programa__ativo=True) & Q(ativo=True))
                qs_programas = (
                    Programa.objects.values(
                        "nome",
                        "nome_fantasia",
                        "safra__safra",
                        "ciclo__ciclo",
                        "versao",
                    )
                    .order_by("safra", "ciclo", "nome")
                    .filter(Q(ativo=True))
                )
                qs_area_total_program = (
                    Plantio.objects.values("programa__nome")
                    .annotate(total=Sum("area_colheita"))
                    .filter(~Q(programa=None) & Q(programa__ativo=True))
                )
                # serializer = AplicacaoSerializer(qs, many=True)
                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs),
                    "dados": qs,
                    "estagios": qs_estagios,
                    "programas": qs_programas,
                    "area_total": qs_area_total_program,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


# --------------------- ---------------------- PROGRAMS API END  --------------------- ----------------------#


def remove_leading_zeros(num):
    return num.lstrip("0")


def adjust_parcelas(parcelas):
    list_parcelas = parcelas.replace("'", "").split(";")
    if len(list_parcelas) == 2:
        return list_parcelas[:-1]
    return parcelas.replace("'", "").split(";")[0:-1]


class ColheitaApiSave(viewsets.ModelViewSet):
    queryset = Colheita.objects.all()
    serializer_class = ColheitaSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    @action(detail=False, methods=["GET", "POST"])
    def save_from_protheus(self, request):
        if request.user.is_authenticated:
            data_json = request.data
            # date_file = request.data["plantio"]
            # data_json = json.load(date_file)
            plantio_query = Plantio.objects.all().filter(
                finalizado_plantio=True,
                finalizado_colheita=False,
                plantio_descontinuado=False,
            )
            deposito_query = Deposito.objects.all()
            succes = 0
            failed = 0
            problem = []
            for i in data_json:
                data = i["Data de Pesagem"]
                romaneio = remove_leading_zeros(str(i["Num Romaneio"]))
                filial = i["Filial"]
                ticket = remove_leading_zeros(str(i["Ticket"]))
                placa = i["Placa do veiculo"]
                motorista = i["Motorista"]
                origem = i["Projeto"]
                origem_id = remove_leading_zeros(str(i["Cod Projeto"]))
                parcelas = adjust_parcelas(i["Parcela"])
                peso_bruto = i["Peso Bruto"]
                peso_tara = i["Peso Tara"]
                peso_liquido = i["Peso Liquido"]
                umidade = i["Umidade Entrada %"]
                impureza = i["Impureza Entrada %"]
                safra = i["Safra"]
                ciclo = i["Ciclo"]
                destino = i["Destino"]
                final_ticket = f"{filial}{ticket}"
                print(i)
                if len(parcelas) > 1:
                    for index, parcela in enumerate(parcelas):
                        peso_bruto_considerado = int(peso_bruto / len(parcelas))
                        peso_tara_considerado = int(peso_tara / len(parcelas))
                        if index + 1 == len(parcelas):
                            if peso_bruto % len(parcelas) != 0:
                                peso_bruto_ajuste = peso_bruto % len(parcelas)
                                peso_bruto_considerado += peso_bruto_ajuste
                            if peso_tara % len(parcelas) != 0:
                                peso_tara_ajuste = peso_tara % len(parcelas)
                                peso_tara_considerado += peso_tara_ajuste
                        peso_liquido_considerado = int(
                            peso_bruto_considerado - peso_tara_considerado
                        )
                        carga = {
                            "data": data,
                            "romaneio": romaneio,
                            "ticket": final_ticket,
                            "placa": placa,
                            "motorista": motorista,
                            "origem": origem,
                            "origem_id": origem_id,
                            "parcela": parcela,
                            "peso_bruto": peso_bruto_considerado,
                            "peso_tara": peso_tara_considerado,
                            "peso_liquido": peso_liquido_considerado,
                            "umidade": umidade,
                            "impureza": impureza,
                            "safra": safra,
                            "ciclo": ciclo,
                            "destino": destino,
                        }
                        try:
                            plantio_id = plantio_query.get(
                                safra__safra=safra,
                                ciclo__ciclo=ciclo,
                                talhao__fazenda__id_d=origem_id,
                                talhao__id_talhao=parcela,
                            )
                            deposito_id = deposito_query.get(pk=destino)

                            if plantio_id and deposito_id:
                                try:
                                    new_carga = Colheita(
                                        plantio=plantio_id,
                                        deposito=deposito_id,
                                        data_colheita=data,
                                        romaneio=romaneio,
                                        placa=placa,
                                        motorista=motorista,
                                        ticket=final_ticket,
                                        peso_tara=peso_tara_considerado,
                                        peso_bruto=peso_bruto_considerado,
                                        umidade=Decimal(umidade),
                                        impureza=Decimal(impureza),
                                    )
                                    new_carga.save()
                                    succes += 1
                                    print(
                                        f"{Fore.GREEN}Nova Carga incluida com sucesso: {new_carga}{Style.RESET_ALL}"
                                    )
                                except Exception as e:
                                    print(
                                        f"Proglema em salvar a carga: {Fore.LIGHTRED_EX}{e}{Style.RESET_ALL}"
                                    )
                                    failed += 1
                                    problem_load = {
                                        "parcela": parcela,
                                        "projeto": origem,
                                        "romaneio": romaneio,
                                        "error": str(e),
                                    }
                                    problem.append(problem_load)
                            print(f"{Fore.BLUE}{deposito_id}{Style.RESET_ALL}")
                            print(f"{Fore.BLUE}{plantio_id}{Style.RESET_ALL}")
                        except Exception as e:
                            print(
                                f"plantio não encontrado - {Fore.LIGHTRED_EX}Origem: {origem} | Parcela: {parcela} | Erro: {e}{Style.RESET_ALL}"
                            )
                            failed += 1
                            problem_load = {
                                "parcela": parcela,
                                "projeto": origem,
                                "romaneio": romaneio,
                                "error": str(e),
                            }
                            problem.append(problem_load)
                        print(carga)
                else:
                    carga = {
                        "data": data,
                        "romaneio": romaneio,
                        "ticket": final_ticket,
                        "placa": placa,
                        "motorista": motorista,
                        "origem": origem,
                        "origem_id": origem_id,
                        "parcela": parcelas[0],
                        "peso_bruto": peso_bruto,
                        "peso_tara": peso_tara,
                        "peso_liquido": peso_liquido,
                        "umidade": umidade,
                        "impureza": impureza,
                        "safra": safra,
                        "ciclo": ciclo,
                        "destino": destino,
                    }
                    try:
                        plantio_id = plantio_query.get(
                            safra__safra=safra,
                            ciclo__ciclo=ciclo,
                            talhao__fazenda__id_d=origem_id,
                            talhao__id_talhao=parcelas[0],
                        )
                        deposito_id = deposito_query.get(pk=destino)
                        if plantio_id and deposito_id:
                            try:
                                new_carga = Colheita(
                                    plantio=plantio_id,
                                    deposito=deposito_id,
                                    data_colheita=data,
                                    romaneio=romaneio,
                                    placa=placa,
                                    motorista=motorista,
                                    ticket=final_ticket,
                                    peso_tara=peso_tara,
                                    peso_bruto=peso_bruto,
                                    umidade=Decimal(umidade),
                                    impureza=Decimal(impureza),
                                )
                                new_carga.save()
                                succes += 1
                                print(
                                    f"{Fore.GREEN}Nova Carga incluida com sucesso: {new_carga}{Style.RESET_ALL}"
                                )
                            except Exception as e:
                                print(
                                    f"Proglema em salvar a carga: {Fore.LIGHTRED_EX}{e}{Style.RESET_ALL}"
                                )
                                failed += 1
                                problem_load = {
                                    "parcela": parcelas[0],
                                    "projeto": origem,
                                    "romaneio": romaneio,
                                    "error": str(e),
                                }
                                problem.append(problem_load)
                        print(f"{Fore.BLUE}{deposito_id}{Style.RESET_ALL}")
                        print(f"{Fore.BLUE}{plantio_id}{Style.RESET_ALL}")
                    except Exception as e:
                        print(
                            f"plantio não encontrado - {Fore.LIGHTRED_EX}Origem: {origem} | Parcela: {parcelas[0]} | Erro: {e}{Style.RESET_ALL}"
                        )
                        failed += 1
                        problem_load = {
                            "parcela": parcelas[0],
                            "projeto": origem,
                            "romaneio": romaneio,
                            "error": str(e),
                        }
                        problem.append(problem_load)
                    print(carga)
                print("\n")
            qs = Colheita.objects.all()
            serializer = ColheitaSerializer(qs, many=True)
            try:
                response = {
                    "msg": f"Cadastro das Cargas efetuado com sucesso!!!",
                    "quantidade": len(serializer.data),
                    "data": {"includes": succes, "notincludes": failed},
                    "failed_load": problem
                    # "data": serializer.data,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


class VisitasConsultasApi(viewsets.ModelViewSet):
    queryset = Visitas.objects.all()
    serializer_class = VisitasSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    @method_decorator(cache_page(300))
    @action(detail=False, methods=["GET"])
    def get_visitas(self, request):
        qs_registros = (
            RegistroVisitas.objects.all()
            .order_by("-visita__id")
            .distinct("visita")
            .select_related("visita", "visita__fazenda")
        )
        serializer_registros = RegistroVisitasSerializer(qs_registros, many=True)

        qs_visitas = (
            Visitas.objects.all()
            .order_by("-id")
            .select_related("fazenda")
            .prefetch_related("projeto")
        )
        serializer_visitas = VisitasSerializer(qs_visitas, many=True)

        response = {
            "msg": "Consulta das Visitas realizada com sucesso!!",
            "data_registros": serializer_registros.data,
            "data_visitas": serializer_visitas.data,
        }
        return Response(response, status=status.HTTP_200_OK)


class RegistroVisitasApi(viewsets.ModelViewSet):
    queryset = RegistroVisitas.objects.all()
    serializer_class = RegistroVisitasSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    @action(detail=False, methods=["GET"])
    def get_registro_visita(self, request, pk=None):
        if request.method == "GET":
            id_filtered = None
            if request.data:
                # id_filtered = request.data["idfilter"]
                print(id_filtered)
                qs = RegistroVisitas.objects.filter(
                    visita_id=id_filtered
                ).select_related("visita", "visita__fazenda")
                # qs = RegistroVisitas.objects.filter(
                #     visita_id=id_filtered
                # ).select_related("visita", "visita__fazenda")
                serialize = RegistroVisitasSerializer(qs, many=True)
                response = {
                    "msg": "Consulta da Visita e as informações Realizada com sucesso!!",
                    "data": serialize.data,
                }
                return Response(response, status.HTTP_200_OK)
            else:
                response = {
                    "msg": "Não foi informado nenhuma visita para Filtro",
                    "data": [],
                }
            return Response(response, status.HTTP_400_BAD_REQUEST)
