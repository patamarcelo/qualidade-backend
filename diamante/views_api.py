from django.shortcuts import render

# Create your views here.

from .serializers import TalhaoSerializer, PlantioSerializer

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


from .models import Talhao, Projeto, Variedade, Plantio, Safra, Ciclo

from functools import reduce


import openpyxl
import json
import csv


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

                    for col in worksheet.iter_rows(min_row=1, max_col=12, max_row=3000):
                        if col[1].value != None and col[0].value != "ID":
                            id_talhao = col[0].value
                            finalizado = True if col[2].value == "Sim" else False
                            area_colher, data_plantio, id_variedade = (
                                col[7].value,
                                col[9].value,
                                col[10].value,
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
                            # plantio = {
                            #     # "id_talhao": id_talhao,
                            #     "id_talhao": talhao_id,
                            #     "finalizado": finalizado,
                            #     "area_colher": area_colher,
                            #     "data_plantio": data_plantio,
                            #     "id_variedade": variedade_id,
                            # }
                            # plantios.append(plantio)
                    # total_plantado = reduce(
                    #     lambda x, y: x + y, [x["area_colher"] for x in plantios]
                    # )
                    # for i in plantios:
                    #     print(i)
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

    @action(detail=False, methods=["GET"])
    def get_plantio(self, request):
        if request.user.is_authenticated:
            try:
                qs = Plantio.objects.values(
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
                ).order_by('talhao__fazenda__nome', 'talhao__id_talhao')

                resumo = {}
                for i in qs:
                    resumo[i["talhao__fazenda__fazenda__nome"]] = {
                        i["talhao__fazenda__nome"]: {}
                    }

                for i in qs:
                    resumo[i["talhao__fazenda__fazenda__nome"]].update(
                        {i["talhao__fazenda__nome"]: {}}
                    )
                for i in qs:
                    resumo[i["talhao__fazenda__fazenda__nome"]][
                        i["talhao__fazenda__nome"]
                    ].update(
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
