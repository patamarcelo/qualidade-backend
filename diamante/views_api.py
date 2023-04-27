from django.shortcuts import render

# Create your views here.

from .serializers import TalhaoSerializer, PlantioSerializer, DefensivoSerializer

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response

import json
from django.http import JsonResponse
from django.core.serializers import serialize
from django.db.models import Q, Sum
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from decimal import *
from django.db.models import Q
from .utils import get_dap, get_prev_app_date, get_quantidade_aplicar


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


# --------------------- --------------------- START TALHAO API --------------------- --------------------- #


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

    @action(detail=True, methods=["POST"])
    def save_plantio_from_farmBox_json(self, request, pk=None):
        if request.user.is_authenticated:
            print(request.data)
            if request.data:
                try:
                    # file = request.FILES["plantio_arroz"]
                    # file_ = open(os.path.join(settings.BASE_DIR, 'filename'))
                    with open("static/files/dataset-2023-2024.json") as user_file:
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
                                    ciclo_1.update(
                                        {cultura_planejada: round(area_total)}
                                    )
                                else:
                                    ciclo_1.update({cultura_planejada: round(area)})
                            if ciclo_json == 2:
                                if ciclo_2.get(cultura_planejada):
                                    area_total = ciclo_2.get(cultura_planejada) + area
                                    ciclo_2.update(
                                        {cultura_planejada: round(area_total)}
                                    )
                                else:
                                    ciclo_2.update({cultura_planejada: round(area)})
                            if ciclo_json == 3:
                                if ciclo_3.get(cultura_planejada):
                                    area_total = ciclo_3.get(cultura_planejada) + area
                                    ciclo_3.update(
                                        {cultura_planejada: round(area_total)}
                                    )
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
                with open("static/files/dataset-2023-2024.json") as user_file:
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
                response = {"message": "Arquivo desconhecido"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- UPDATE PLANTIO API --------------------- ----------------------#

    # --------------------- ---------------------- UPDATE PLANTIO API FROM FARMBOX START --------------------- ----------------------#
    @action(detail=True, methods=["GET"])
    def update_plantio_from_farmBox(self, request, pk=None):
        if request.user.is_authenticated:
            try:
                # file = request.FILES["plantio_arroz"]
                # file_ = open(os.path.join(settings.BASE_DIR, 'filename'))
                date_file = "2023-04-18"
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

                count_total = 0
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
                        try:
                            field_to_update = Plantio.objects.filter(
                                safra=safra, ciclo=ciclo, talhao=talhao_id
                            )[0]

                            if date_plantio:
                                field_to_update.data_plantio = date_plantio

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
                                f"{Fore.GREEN}Plantio Alterado com sucesso: {field_to_update}{Style.RESET_ALL}"
                            )
                            print("\n")
                            count_total += 1
                        except Exception as e:
                            print(
                                f"{Fore.RED}Problema em salvar o plantio: {talhao_id} - {safra} - {ciclo}{Style.RESET_ALL}{e}"
                            )
                qs_plantio = Plantio.objects.filter(safra__safra="2023/2024")

                total_plantado = Plantio.objects.filter(
                    safra__safra="2023/2024", ciclo__ciclo="1"
                ).aggregate(Sum("area_colheita"))

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

    @action(detail=False, methods=["GET"])
    def get_plantio(self, request):
        if request.user.is_authenticated:
            try:
                qs = (
                    Plantio.objects.values(
                        "safra__safra",
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
                    .filter(safra__safra="2023/2024", ciclo__ciclo="1")
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

                area_total = Plantio.objects.aggregate(Sum("area_colheita"))

                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "total_return": len(qs),
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
                                    talhao__id_unico=talhao_id.id_unico
                                ).update(
                                    finalizado_colheita=finalizado,
                                    safra=safra,
                                    ciclo=ciclo,
                                )

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

    @action(detail=False, methods=["GET"])
    def get_plantio_operacoes_detail(self, request):
        if request.user.is_authenticated:
            try:
                safra_2022_2023 = 0
                safra_2023_2024 = 1
                safra = Safra.objects.all()[safra_2023_2024]
                ciclo_1 = 0
                ciclo_2 = 1
                ciclo_3 = 2
                ciclo = Ciclo.objects.all()[ciclo_1]
                qs_plantio = (
                    Plantio.objects.values(
                        "id",
                        "talhao__id_talhao",
                        "talhao_id",
                        "safra__safra",
                        "ciclo__ciclo",
                        "talhao__fazenda__nome",
                        "variedade__nome_fantasia",
                        "variedade__cultura__cultura",
                        "area_colheita",
                        "data_plantio",
                        "programa",
                        "programa_id"
                        # "get_cronograma_programa",
                    )
                    .filter(~Q(programa_id=None))
                    .filter(safra=safra, ciclo=ciclo)
                )
                ids_list_plantio = qs_plantio.values("id")
                qs_programas = Operacao.objects.values(
                    "estagio", "programa_id", "prazo_dap", "id"
                )
                qs_aplicacoes = (
                    Aplicacao.objects.values(
                        "defensivo__produto",
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
                        operacao__programa__safra=safra, operacao__programa__ciclo=ciclo
                    )
                )

                final_result = {i["talhao__fazenda__nome"]: {} for i in qs_plantio}

                {
                    final_result[i["talhao__fazenda__nome"]].update(
                        {
                            i["talhao__id_talhao"]: {
                                "safra": i["safra__safra"],
                                "ciclo": i["ciclo__ciclo"],
                                "cultura": i["variedade__cultura__cultura"],
                                "variedade": i["variedade__nome_fantasia"],
                                "plantio_id": i["id"],
                                "area_colheita": i["area_colheita"],
                                "data_plantio": i["data_plantio"],
                                "dap": get_dap(i["data_plantio"]),
                                "programa": i["programa"],
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

                # crono_list = [
                #     (x.get_detail_cronograma_and_aplication, x.get_dap)
                #     for x in Plantio.objects.filter(id__in=ids_list)
                # ]

                # final_return = []
                # for i in crono_list:
                #     dict_up = qs.filter(id=i[0][0]["id"])[0]
                #     dict_up.update({"DAP": i[1]})
                #     dict_up.update({"cronograma": i[0]})
                #     final_return.append(dict_up)

                # fazendas = set([x["talhao__fazenda__nome"] for x in qs_plantio])

                response = {
                    "msg": f"Consulta realizada com sucesso!!",
                    "fazendas": final_result,
                    "total_return_plantio": len(qs_plantio),
                    "dados_plantio": qs_plantio,
                    "total_return_aplicacoes": len(qs_aplicacoes),
                    "dados_aplicacoes": qs_aplicacoes,
                }
                return Response(response, status=status.HTTP_200_OK)
            except Exception as e:
                response = {"message": f"Ocorreu um Erro: {e}"}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
        else:
            response = {"message": "Você precisa estar logado!!!"}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

    # --------------------- ---------------------- PLANTIO APLICACOES API END --------------------- ----------------------#

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
