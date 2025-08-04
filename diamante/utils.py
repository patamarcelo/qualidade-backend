from datetime import timedelta
import datetime
import sys
import time
import threading
import os

today = datetime.date.today()

import requests
import json

from qualidade_project.settings import FARMBOX_ID

import dropbox
from dropbox.sharing import RequestedVisibility
from django.conf import settings


from django.db.models import Q, Sum, F
from django.db.models.functions import Coalesce, Round

from django.db import transaction
import time

from pathlib import Path
from django.core.cache import cache
from decimal import Decimal

import pandas as pd
from collections import defaultdict


# pr_mungo = Programa.objects.all()[2]
# pr_caupi = Programa.objects.all()[1]
# pr_rr = Programa.objects.all()[4]
# pr_conven = Programa.objects.all()[3]

# pl_mungo = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Feijão", finalizado_plantio=True).filter(programa=pr_mungo)
# pl_caupi = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Feijão", finalizado_plantio=True).filter(programa=pr_caupi)
# pl_rr = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Soja", finalizado_plantio=True).filter(programa=pr_rr)
# pl_conv = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Soja", finalizado_plantio=True).filter(programa=pr_conven)

# op = Operacao.objects.filter(estagio=current_op, programa=)[0].operation_to_dict

# index = get_index_dict_estagio(i.cronograma_programa, current_op)
# if i.cronograma_programa[index]['aplicado'] == False:
# i.cronograma_programa[index]['produtos'] = op
# i.save()


# ------------------------------------------------------------------------------------ SAFRA 2023/2024 - CICLO=2 --------------#

"""
from diamante.models import Plantio, Programa, Operacao
from diamante.utils import *
pr_mungo = Programa.objects.filter(safra__safra="2023/2024", ciclo__ciclo="2", cultura__cultura="Feijão")[1]
pr_caupi  = Programa.objects.filter(safra__safra="2023/2024", ciclo__ciclo="2", cultura__cultura="Feijão")[0]
pr_soja = Programa.objects.filter(safra__safra="2023/2024", ciclo__ciclo="2", cultura__cultura="Soja")[0]
pr_olimpo = Programa.objects.filter(safra__safra="2023/2024", ciclo__ciclo="2", cultura__cultura="Soja")[1]



pl = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="2")
pl_mungo = pl.filter(variedade__variedade="Feijão Mungo Verde")
pl_caupi = pl.filter(variedade__variedade="Feijão Caupi")
pl_soja = pl.filter(variedade__cultura__cultura="Soja")
pl_olimpo = pl.filter(variedade__variedade="Soja Olimpo IPRO")

"""

"""sumary_line

Keyword arguments:
argument -- description
Return: return_description

for i in pl_done:
...     estagio_added = op
...     date_prev = get_prev_app_date(i.data_plantio, 25)
...     estagio_added['data prevista'] = format_date_json(date_prev)
...     i.cronograma_programa.append(estagio_added)
...     i.save()

for i in pl_mungo:
...     index = get_index_dict_estagio(i.cronograma_programa, "12 DIAS")
...     new_date = format_date_json(get_prev_app_date(i.data_plantio, 12))
...     i.cronograma_programa[index].update({'data prevista': new_date})
...     print(i.cronograma_programa[index]['data prevista'])


for i in pl_soja_ok:
...     days = 12
...     program = "2º TRIFÓLIO (V2)"
...     index = get_index_dict_estagio(i.cronograma_programa, program)
...     new_date = format_date_json(get_prev_app_date(i.data_plantio, days))
...     i.cronograma_programa[index].update({'data prevista': new_date, 'dap': days})
...     i.save()
...
>>> for i in pl_soja_ok:
...     days = 17
...     program = "3º TRIFÓLIO (V3)"
...     index = get_index_dict_estagio(i.cronograma_programa, program)
...     new_date = format_date_json(get_prev_app_date(i.data_plantio, days))
...     i.cronograma_programa[index].update({'data prevista': new_date, 'dap': days})
...     i.save()
...

"""


# ------------------------------------------------------------------------------------ SAFRA 2023/2024 - CICLO=2 --------------#


# ------------------------------------------------------------------------------------ SAFRA 2023/2024 - CICLO=3 --------------#

"""
from diamante.models import Plantio, Programa, Operacao
from diamante.utils import *
pr_arroz = Programa.objects.filter(safra__safra="2023/2024", ciclo__ciclo="3", cultura__cultura="Arroz")[0]

pl = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="3")
pl_arroz = pl.filter(variedade__cultura__cultura="Arroz")

"""
# ------------------------------------------------------------------------------------ SAFRA 2023/2024 - CICLO=3 --------------#


# ------------------------------------------------------------------------------------ START DUPLICANDO PROGRAMAS --------------#
"""        _START DUPLICANDO PROGRAMAS_

    
from diamante.models import Programa, Operacao , Aplicacao
p_a = Programa.objects.filter(cultura__cultura="Arroz")
p_a_424 = p_a[1]
p_a_pam = p_a[2]
apl = Aplicacao.objects.filter(operacao__programa=p_a_424)
op_pam = Operacao.objects.filter(programa=p_a_pam)
for i in op_pam:
    for j in apl:
            if i.estagio == j.operacao.estagio:
                    new_op = j
                    new_op.id = None
                    new_op.pk = None
                    new_op._state.adding = True
                    new_op.operacao = i
                    new_op.save()


Returns:
        _type_: _description_
    """

# ------------------------------------------------------------------------------------ END DUPLICANDO PROGRAMAS --------------#


def get_dap(data_plantio):
    if data_plantio:
        dap = 0
        today = datetime.date.today()
        if type(data_plantio) == str:
            date_ftime = datetime.datetime.strptime(data_plantio, "%Y-%m-%d")
            today_st = datetime.datetime.now()
            dap = today_st - date_ftime
            dap = dap.days + 1
        elif type(data_plantio) != str:
            dap = today - data_plantio
            dap = dap.days + 1
        return dap
    else:
        return 0


def get_prev_app_date(data_plantio, prazo_dap):
    real_prazo = prazo_dap - 1 if prazo_dap > 0 else 0
    if data_plantio:
        prev_app = data_plantio + datetime.timedelta(days=real_prazo)
    else:
        prev_app = "Sem Data Plantio Informada"
    return prev_app


def get_quantidade_aplicar(dose, area_colehita):
    total = 0
    if dose and area_colehita:
        total = dose * area_colehita
    else:
        print("problema em calcular o total a aplicar")
    return total


def get_base_date(data_inicial, today=today):
    today = datetime.date.today()
    if data_inicial > today:
        return data_inicial
    else:
        return today


def format_date_json(date, timedelta=None):
    if timedelta:
        date_formated = datetime.datetime.strptime(date, "%Y-%m-%d") + timedelta
    else:
        date_formated = date
    if type(date_formated) is not str:
        date_formated = date_formated.strftime("%Y-%m-%d")
    return date_formated


def calc_total(area, dose):
    areaF = float(area)
    total = dose * areaF
    totalF = round(total, 3)
    return str(totalF)


def get_index_dict_prod(lista_produtos, find_product):
    # Lista Produtos: i.cronograma_programa[5]['produtos']
    v4_prod = lista_produtos
    # ork = [ (x,n) for x,n in enumerate( v4_prod) if n['produto'] == 'ORKESTRA']
    ork = [(x, n) for x, n in enumerate(v4_prod) if n["produto"] == find_product]
    if ork:
        index = ork[0][0]
    else:
        index = None
    return index
    # i.cronograma_programa[5]['produtos'][index] = {'dose': '0.600', 'tipo': 'fungicida', 'produto': 'OPERA', 'quantidade aplicar': calc_total(i.area_colheita, 0.600)}


def get_index_dict_estagio(lista_programa, find_estagio):
    index = next(
        (
            i
            for i, d in enumerate(lista_programa)
            if "estagio" in d and d["estagio"] == find_estagio
            # if (
            #     ("estagio_id" in d and d["estagio_id"] == find_estagio)  # busca por ID
            #     or
            #     ("estagio" in d and d["estagio"] == find_estagio)        # fallback por nome
            # )
        ),
        None,
    )
    return index


def alter_programa_and_save(query, operation, current_op_products):
    for i in query:
        try:
            index = get_index_dict_estagio(i.cronograma_programa, operation)
            if i.cronograma_programa[index]["aplicado"] == False:
                i.cronograma_programa[index]["produtos"] = current_op_products
                i.save()
                print(f"Alteração de programa salva com sucesso: {i}")
        except Exception as e:
            print("Erro ao Salvar a alteração no programa do  plantio", e)


def alter_dap_programa_and_save(query, dap, current_op):
    for i in query:
        try:
            days = dap
            program = current_op
            index = get_index_dict_estagio(i.cronograma_programa, program)
            if i.cronograma_programa[index]["aplicado"] == False:
                new_date = format_date_json(get_prev_app_date(i.data_plantio, days))
                i.cronograma_programa[index].update(
                    {"data prevista": new_date, "dap": days}
                )
                i.save()
        except Exception as e:
            print("Erro ao Salvar a alteração no programa do  plantio", e)


def invalidate_plantio_cache(safra, ciclo):
    cache_key = f"get_plantio_operacoes_detail_json_program_qs_plantio_{safra}_{ciclo}"
    print("invalidando o cache", cache_key)
    cache_key_qs_plantio_get_plantio_operacoes_detail = (
        f"get_plantio_operacoes_detail_qs_plantio_{safra}_{ciclo}"
    )
    cache_key_qs_plantio_map = f"get_plantio_map_{safra}_{ciclo}"
    cache_key_web = (
        f"get_plantio_operacoes_detail_json_program_qs_plantio_web_{safra}_{ciclo}"
    )

    cache.delete(cache_key)
    cache.delete(cache_key_web)
    cache.delete(cache_key_qs_plantio_get_plantio_operacoes_detail)
    cache.delete(cache_key_qs_plantio_map)


def admin_form_alter_programa_and_save(
    query,
    operation,
    current_op_products,
    difDap,
    newDap,
    nome_estagio_alterado,
    estagio_alterado,
):
    start_time = time.time()
    print(f"Start time: {start_time}")
    from diamante.models import Plantio

    updated_objects = []

    fetch_time = time.time()
    print(f"Time after fetching objects: {fetch_time - start_time} seconds")
    for i in query:
        try:
            loop_start_time = time.time()
            index = get_index_dict_estagio(i.cronograma_programa, operation)
            print("Index: ", index)
            get_index_time = time.time()
            print(f"Time to get index: {get_index_time - loop_start_time} seconds")
            if index:
                if nome_estagio_alterado == True:
                    i.cronograma_programa[index]["estagio"] = estagio_alterado
                if i.cronograma_programa[index]["aplicado"] == False:
                    i.cronograma_programa[index]["produtos"] = current_op_products
                    if difDap == True:
                        days = newDap
                        new_date = format_date_json(
                            get_prev_app_date(i.data_plantio, days)
                        )
                        i.cronograma_programa[index].update(
                            {"data prevista": new_date, "dap": days}
                        )
                    updated_objects.append(i)
                    # i.save()
                    print(f"Alteração de programa salva com sucesso: {i}")
                update_time = time.time()
                print(
                    f"Time to update cronograma_programa: {update_time - get_index_time} seconds"
                )
            else:
                operation_to_add = {
                    "dap": newDap,
                    "estagio": operation,
                    "aplicado": False,
                    "enviado_farmbox": False,
                    "produtos": current_op_products,
                    "data prevista": format_date_json(
                        get_prev_app_date(i.data_plantio, newDap)
                    ),
                }
                i.cronograma_programa.append(operation_to_add)
                updated_objects.append(i)
                # i.save()
                print(f"Estágio incluído com sucesso: {i}")
        except Exception as e:
            print("Erro ao Salvar a alteração no programa do  plantio", e)

    if updated_objects:
        print("atualizando Banco de Dados")
        bulk_update_start_time = time.time()
        with transaction.atomic():
            Plantio.objects.bulk_update(updated_objects, ["cronograma_programa"])
        print("atualizando Banco de Dados: Finalizado")
        bulk_update_time = time.time()
        print(
            f"Time for bulk update: {bulk_update_time - bulk_update_start_time} seconds"
        )

        # Usando safra e ciclo do primeiro objeto atualizado (assumindo que todos são do mesmo safra/ciclo)
        safra = updated_objects[0].safra.safra
        ciclo = updated_objects[0].ciclo.ciclo
        invalidate_plantio_cache(safra, ciclo)

    end_time = time.time()
    print(f"Total time: {end_time - start_time} seconds")


def admin_form_remove_index(query, operation):
    for i in query:
        try:
            index = get_index_dict_estagio(i.cronograma_programa, operation)
            if index:
                if i.cronograma_programa[index]["aplicado"] == False:
                    print("removido : ", i.cronograma_programa[index])
                    i.cronograma_programa.pop(index)
                    i.save()
        except Exception as e:
            print("Erro ao Remover o Estágio do plantio", e)


def close_plantation_and_productivity(id_plantation_farm, close_date, product):
    # id_plantation = 193351
    # close_date = "2023-11-10"
    # producti = 40.20
    id_plantation = id_plantation_farm
    url = f"https://farmbox.cc/api/v1/plantations/{id_plantation}"
    payload = {"id": id_plantation, "closed_date": close_date, "productivity": product}
    headers = {
        "content-type": "application/json",
        "Authorization": FARMBOX_ID,
    }
    response = requests.put(url, data=json.dumps(payload), headers=headers)
    print("response:", response.status_code, response.text)
    return response


def duplicate_existing_operations_program(old_program, new_program, operacao_model):
    print("pegando as operações a serem duplicadas")
    old_operations = operacao_model.objects.filter(programa=old_program, ativo=True)
    try:
        for op in old_operations:
            new_op = op
            new_op.id = None
            new_op.pk = None
            new_op._state.adding = True
            new_op.programa = new_program
            new_op.save()
            print(f"{op} Duplicada com sucesso!!")
    except Exception as e:
        print(f"Erro ao Duplicar as Operações do Programa: {e}")


def duplicate_existing_operations_program_and_applications(
    old_program, new_program, operacao_model, aplicacao_model, keep_price=False
):

    # THIS TRY BLOCK NOT TESTED YET
    try:
        duplicate_existing_operations_program(old_program, new_program, operacao_model)
        print("\n")
        print("Todas os estágios duplicados com sucesso...")
    except Exception as e:
        print(f"Error ao gerar as aplicacoes dentro da funcao: {e}")

    try:
        print("Pegando os estágios e apliaccoes a serem duplicadas")
        new_operations = operacao_model.objects.filter(programa=new_program, ativo=True)
        old_aplications = aplicacao_model.objects.filter(
            operacao__programa=old_program, ativo=True
        )
        for op in new_operations:
            for ap in old_aplications:
                if op.estagio == ap.operacao.estagio:
                    new_op = ap
                    new_op.id = None
                    new_op.pk = None
                    new_op._state.adding = True
                    new_op.operacao = op
                    new_op.operacao.programa = new_program
                    if keep_price == False:
                        print("nao deve manter os preços antigos")
                        new_op.preco = None
                        new_op.valor_final = 0
                        new_op.valor_aplicacao = 0
                        new_op.moeda = None
                    new_op.save()
                    print(f"Aplicação: {ap} e Operação: {op} duplicadas com sucesso!!")
    except Exception as e:
        print(f"Erro ao Duplicar as Operações do Programa com as Aplicações: {e}")


def get_cargas_model(safra_filter, ciclo_filter, colheita):
    print(safra_filter, ciclo_filter, colheita)
    cargas_model = [
        x
        for x in colheita.objects.values(
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
    ]
    return cargas_model


v6_1_conv = {
    "dap": 38,
    "estagio": "6º TRIFOLIO ( V6.1 )",
    "aplicado": False,
    "produtos": [
        {
            "dose": "0.300",
            "tipo": "oleo_mineral_vegetal",
            "produto": "FIX OIL",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.015",
            "tipo": "adjuvante",
            "produto": "LEGAT REDUCE",
            "quantidade aplicar": "",
        },
        {
            "dose": "1.000",
            "tipo": "fungicida",
            "produto": "MANCOZEB",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.060",
            "tipo": "nutricao",
            "produto": "COBRE",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.600",
            "tipo": "fungicida",
            "produto": "OPERA",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.030",
            "tipo": "inseticida",
            "produto": "Demacor",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.022",
            "tipo": "inseticida",
            "produto": "ABAMECTINA 400",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.080",
            "tipo": "inseticida",
            "produto": "KAISO 250",
            "quantidade aplicar": "",
        },
    ],
    "data prevista": "",
}
v6_2_conv = {
    "dap": 38,
    "estagio": "6º TRIFOLIO ( V6.2 )",
    "aplicado": False,
    "produtos": [
        {
            "dose": "1.500",
            "tipo": "biologico",
            "produto": "MIX BT's",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.400",
            "tipo": "nutricao",
            "produto": "SÍLICA",
            "quantidade aplicar": "",
        },
        {
            "dose": "1.000",
            "tipo": "nutricao",
            "produto": "SULFATO DE MAGNÉSIO",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.200",
            "tipo": "nutricao",
            "produto": "ORGANO BORO",
            "quantidade aplicar": "",
        },
    ],
    "data prevista": "",
}
v6_1_rr = {
    "dap": 31,
    "estagio": "6º TRIFOLIO ( V6.1 )",
    "aplicado": False,
    "produtos": [
        {
            "dose": "0.300",
            "tipo": "oleo_mineral_vegetal",
            "produto": "FIX OIL",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.015",
            "tipo": "adjuvante",
            "produto": "LEGAT REDUCE",
            "quantidade aplicar": "",
        },
        {
            "dose": "1.000",
            "tipo": "fungicida",
            "produto": "MANCOZEB",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.060",
            "tipo": "nutricao",
            "produto": "COBRE",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.600",
            "tipo": "fungicida",
            "produto": "OPERA",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.022",
            "tipo": "inseticida",
            "produto": "ABAMECTINA 400",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.030",
            "tipo": "inseticida",
            "produto": "Demacor",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.080",
            "tipo": "inseticida",
            "produto": "KAISO 250",
            "quantidade aplicar": "",
        },
    ],
    "data prevista": "",
}
v6_2_rr = {
    "dap": 31,
    "estagio": "6º TRIFOLIO ( V6.2 )",
    "aplicado": False,
    "produtos": [
        {
            "dose": "1.500",
            "tipo": "biologico",
            "produto": "MIX BT's",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.400",
            "tipo": "nutricao",
            "produto": "SÍLICA",
            "quantidade aplicar": "",
        },
        {
            "dose": "1.000",
            "tipo": "nutricao",
            "produto": "SULFATO DE MAGNÉSIO",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.200",
            "tipo": "nutricao",
            "produto": "ORGANO BORO",
            "quantidade aplicar": "",
        },
    ],
    "data prevista": "",
}


def get_long_lived_link(file_path):
    # Dropbox access token
    access_token = (
        settings.DROPBOX_OAUTH2_REFRESH_TOKEN
    )  # Replace with your actual access token

    # Initialize Dropbox SDK
    dbx = dropbox.Dropbox(access_token)

    # Convert the temporary link to a long-lived one
    # long_lived_link = dbx.sharing_create_shared_link(result.link).url
    long_lived_link = dbx.sharing_create_shared_link_with_settings(file_path).url

    return long_lived_link


# Example usage:
# file_path = "/path/to/your/file.txt"
# long_lived_link = get_long_lived_link(file_path)
# print("Long-lived link:", long_lived_link)


dictFarm = [
    {"id": 11936, "name": "Fazenda Safira", "fazenda": "Campo Guapo", "protId": "0208"},
    {"id": 11937, "name": "Fazenda Tucano", "fazenda": "Diamante", "protId": "0202"},
    {"id": 11938, "name": "Fazenda Jacaré", "fazenda": "Diamante", "protId": "0202"},
    {"id": 11939, "name": "Fazenda Capivara", "fazenda": "Diamante", "protId": "0202"},
    {"id": 11940, "name": "Fazenda Tuiuiu", "fazenda": "Diamante", "protId": "0202"},
    {"id": 11941, "name": "Fazenda Cervo", "fazenda": "Diamante", "protId": "0202"},
    {"id": 11942, "name": "Fazenda Lago Verde", "fazenda": "Lago Verde", "protId": ""},
    {
        "id": 11943,
        "name": "Fazenda Praia Alta",
        "fazenda": "Diamante",
        "protId": "0202",
    },
    {
        "id": 11944,
        "name": "Fazenda Campo Guapo",
        "fazenda": "Campo Guapo",
        "protId": "0208",
    },
    {
        "id": 11945,
        "name": "Fazenda Cacique",
        "fazenda": "Campo Guapo",
        "protId": "0208",
    },
    {
        "id": 11946,
        "name": "Fazenda Benção de Deus",
        "fazenda": "Bencao de Deus",
        "protId": "0206",
    },
    {"id": 11947, "name": "Fazenda Santa Maria", "fazenda": "", "protId": ""},
    {"id": 11948, "name": "Fazenda Eldorado", "fazenda": "", "protId": ""},
    {"id": 11949, "name": "Fazenda Fazendinha", "fazenda": "", "protId": "0207"},
    {"id": 11950, "name": "Fazenda Novo Acordo", "fazenda": "", "protId": ""},
    {"id": 11951, "name": "Fazenda Ouro Verde", "fazenda": "", "protId": "0204"},
    {"id": 12103, "name": "Fazenda 5 Estrelas ", "fazenda": "", "protId": ""},
    {"id": 12104, "name": "Fazenda Pau Brasil", "fazenda": "", "protId": ""},
    {"id": 12105, "name": "Fazenda Biguá", "fazenda": "", "protId": ""},
]


# FOR FARMBOX API INTEGRATION


def get_date(days_before):
    today = datetime.datetime.now() - datetime.timedelta(days=days_before)

    format_date = datetime.datetime.strftime(today, "%Y-%m-%d %H:%M")
    return format_date


def get_miliseconds(date_from):
    # dt_obj = datetime.strptime("18.04.2023", "%d.%m.%Y %H:%M:%S,%f")
    dt_obj = datetime.datetime.strptime(f"{date_from}", "%Y-%m-%d %H:%M")
    millisec = dt_obj.timestamp() * 1000
    print(millisec)
    return millisec


class Spinner:
    def __init__(self, message="Processing"):
        self.message = message
        self.done = False
        self.spinner_cycle = ["-", "\\", "|", "/"]

    def spinner_task(self):
        while not self.done:
            for spinner in self.spinner_cycle:
                sys.stdout.write(f"\r{self.message} {spinner}")
                sys.stdout.flush()
                time.sleep(0.1)

    def __enter__(self):
        self.done = False
        self.spinner_thread = threading.Thread(target=self.spinner_task)
        self.spinner_thread.start()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.done = True
        self.spinner_thread.join()
        sys.stdout.write("\r")
        sys.stdout.flush()


def is_older_than_7_days(date_string):
    # Define the date format to match the input date string
    date_format = "%Y-%m-%d"

    # Convert the date string to a datetime object
    input_date = datetime.datetime.strptime(date_string, date_format)

    # Calculate the date 30 days ago from today
    thirty_days_ago = datetime.datetime.today() - datetime.timedelta(days=7)

    # Check if the input date is older than 30 days ago
    return input_date > thirty_days_ago


def load_localization_data():
    from .models import Plantio

    """
    Loads and returns the localization.json data as a list of objects.
    """
    file_path = Path(__file__).resolve().parent / "utils/localization-1.json"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            updated = 0
            for item in data:
                id_farmbox = item.get("ID FarmBox")
                date_str = item.get("prev_plantio")  # Adjust key name if different
                fazenda = item.get("Projeto")
                parcela = item.get("Talhao")
                if fazenda == "Projeto Benção de Deus":
                    if date_str:
                        format_date = datetime.datetime.strptime(
                            date_str, "%m/%d/%y"
                        ).date()
                        print(
                            "Fazenda: ",
                            fazenda,
                            "Talhão: ",
                            parcela,
                            "Prev Plantio: ",
                            format_date,
                            "idFarm: ",
                            id_farmbox,
                        )
                        try:
                            plantio = Plantio.objects.get(id_farmbox=id_farmbox)
                            plantio.data_prevista_plantio = format_date
                            plantio.save()
                            updated += 1
                        except Plantio.DoesNotExist:
                            print(f"❌ Plantio not found for idFarmbox={id_farmbox}")
                        except Exception as e:
                            print(f"⚠️ Error updating idFarmbox={id_farmbox}: {e}")
            print(f"✅ Finished. {updated} records updated.")
        return data
    except Exception as e:
        print(f"Error loading localization data: {e}")
        return []


def save_program_cost():
    from .models import Aplicacao

    pr_arroz = Aplicacao.objects.filter(
        operacao__programa__safra__safra="2025/2026",
        operacao__programa__ciclo__ciclo="3",
    ).filter(Q(preco__isnull=True) | Q(preco=0))
    print("arroz total: ", len(pr_arroz))
    print("prArroz: ", pr_arroz[0])
    file_path = Path(__file__).resolve().parent / "utils/custos-programas.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        updated = 0
        for item in data:
            defensivo = item.get("Defensivo")
            preco = item.get("Preço")
            moeda = item.get("Moeda")
            print("Defensivo: ", defensivo, "Preço :", preco, "Moeda: ", moeda)


def save_program_cost():
    from .models import Aplicacao, MoedaChoices

    pr_arroz = Aplicacao.objects.filter(
        operacao__programa__safra__safra="2025/2026",
        operacao__programa__ciclo__ciclo="3",
    ).filter(Q(preco__isnull=True) | Q(preco=0))

    print("Total de aplicações sem preço:", pr_arroz.count())

    file_path = Path(__file__).resolve().parent / "utils/custos-programas.json"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0

    for item in data:
        nome_defensivo = item.get("Defensivo", "").strip().lower()
        preco_raw = item.get("Preço")
        moeda_raw = item.get("Moeda", "").strip().upper()

        # Validação mínima
        if not nome_defensivo or not preco_raw:
            continue

        try:
            preco = Decimal(str(preco_raw).replace(",", "."))
        except Exception as e:
            print(f"❌ Erro ao converter preço de {nome_defensivo}: {e}")
            continue

        moeda = MoedaChoices.BRL if "R$" in moeda_raw else MoedaChoices.USD

        # Busca por defensivos com nome correspondente (case-insensitive)
        matched = pr_arroz.filter(defensivo__produto__iexact=nome_defensivo)

        if matched.exists():
            for app in matched:
                app.preco = preco
                app.moeda = moeda
                app.save()
                updated += 1
                print(
                    f"✅ Atualizado: {app.defensivo} → Preço: {preco} | Moeda: {moeda}"
                )
        else:
            print(f"⚠️ Não encontrado: '{nome_defensivo}' entre as aplicações sem preço")

    print(f"✅ Total atualizados: {updated}")


def atualizar_datas_previstas_plantio():
    from .models import Plantio

    caminho_arquivo_excel = os.path.join(
        os.path.dirname(__file__), "utils", "datas_plantio-2.xlsx"
    )

    """
    Atualiza o campo data_prevista_plantio do modelo Plantio
    com base no ID FarmBox presente na aba "Plantio" do arquivo Excel.
    """
    try:
        df = pd.read_excel(caminho_arquivo_excel, sheet_name="Plantio")

        # Remove nulos, converte para inteiro (para remover o .0) e depois para string
        df["ID FarmBox"] = df["ID FarmBox"].apply(
            lambda x: str(int(x)).strip() if pd.notna(x) else None
        )

        # Coleta os IDs únicos válidos
        ids_farmbox = df["ID FarmBox"].dropna().unique().tolist()
        # Filtra apenas os Plantios necessários
        plantios_dict = {
            str(p.id_farmbox).strip(): p
            for p in Plantio.objects.filter(id_farmbox__in=ids_farmbox)
        }

        atualizados = 0
        nao_encontrados = []
        objetos_para_salvar = []

        # for _, row in df.head(65).iterrows():
        for _, row in df.iterrows():
            id_farmbox = str(row.get("ID FarmBox", "")).strip()
            data_prevista = row.get("Data Prevista Plantio")
            print("data prevista: ", data_prevista)
            print("id Farmbox: ", id_farmbox)

            if pd.isna(id_farmbox) or pd.isna(data_prevista):
                continue

            try:
                # Converte a data se necessário
                if isinstance(data_prevista, str):
                    data_formatada = datetime.datetime.strptime(
                        data_prevista, "%d/%m/%Y"
                    ).date()
                elif isinstance(data_prevista, datetime.datetime):
                    data_formatada = data_prevista.date()
                else:
                    continue
            except Exception:
                continue

            plantio = plantios_dict.get(id_farmbox)
            if plantio:
                print("✅ plantio encontrado e data formatada: ", data_formatada)
                plantio.data_prevista_plantio = data_formatada
                objetos_para_salvar.append(plantio)
                atualizados += 1
            else:
                nao_encontrados.append(id_farmbox)

        with transaction.atomic():
            if objetos_para_salvar:
                Plantio.objects.bulk_update(
                    objetos_para_salvar, ["data_prevista_plantio"]
                )

        print(f"✅ {atualizados} registros atualizados com sucesso.")
        if nao_encontrados:
            print(f"⚠️ IDs não encontrados: {', '.join(nao_encontrados)}")

    except Exception as e:
        print(f"❌ Erro ao atualizar dados: {str(e)}")


def set_variety_plantations():
    from .models import Plantio, Variedade

    data_limite = datetime.date(2025, 11, 4)

    # Filtro principal
    plantios = Plantio.objects.filter(
        safra__safra="2025/2026",
        ciclo__ciclo="3",
        variedade__cultura__cultura="Arroz",
        data_prevista_plantio__isnull=False,
        id_farmbox__isnull=False,
    )

    # Variedades alvo
    variedade_antes = Variedade.objects.get(id=61)
    variedade_depois = Variedade.objects.get(id=62)

    for plantio in plantios:
        data = plantio.data_prevista_plantio
        nova_variedade = variedade_antes if data < data_limite else variedade_depois

        # Atualiza o campo no banco
        plantio.variedade = nova_variedade
        plantio.save(update_fields=["variedade"])

        # Monta payload para a API
        payload = {
            "planned_variety_id": nova_variedade.id_farmbox,
            "planned_date": data.strftime("%Y-%m-%d"),
        }

        # Envia PUT para Farmbox
        url = f"https://farmbox.cc/api/v1/plantations/{plantio.id_farmbox}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": FARMBOX_ID,
        }

        try:
            response = requests.put(url, data=json.dumps(payload), headers=headers)
            print(
                f"✅ Plantio {plantio} (Farmbox ID: {plantio.id_farmbox}) atualizado para variedade {nova_variedade.variedade} - {nova_variedade.id_farmbox}"
            )
            print(f"   ▶️ Status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"❌ Erro ao atualizar plantio {plantio}: {e}")


emails_list_by_farm = [
    {
        "projetos": ["Fazenda Benção de Deus"],
        "emails_abertura_st": [
            "matheus.silva@diamanteagricola.com.br",
            "gisely.alencar@diamanteagricola.com.br",
            "juliana.silva@diamanteagricola.com.br",
        ],
    },
    {
        "projetos": ["Fazenda Cacique", "Fazenda Campo Guapo", "Fazenda Safira"],
        "emails_abertura_st": [
            "Willian.junior@diamanteagricola.com.br",
            "joao.neto@diamanteagricola.com.br",
        ],
    },
    {
        "projetos": [
            "Fazenda Capivara",
            "Fazenda Cervo",
            "Fazenda Jacaré",
            "Fazenda Tucano",
            "Fazenda Tuiuiu",
        ],
        "emails_abertura_st": [
            "lara.rodrigues@diamanteagricola.com.br",
            "jordana.souza@diamanteagricola.com.br",
        ],
    },
    {
        "projetos": [
            "Fazenda Lago Verde",
            "Fazenda Fazendinha",
            "Fazenda Santa Maria",
        ],
        "emails_abertura_st": [
            "marcelo.pata@diamanteagricola.com.br",
            "juliana.silva@diamanteagricola.com.br",
            "gisely.alencar@diamanteagricola.com.br",
        ],
    },
]



def create_emails():
    from .models import Projeto, EmailAberturaST

    for entry in emails_list_by_farm:
        for nome_projeto in entry["projetos"]:
            # Ajuste de nome conforme regra antiga
            new_name = nome_projeto.replace("Fazenda", "Projeto").replace(
                "Cacique", "Cacíque"
            )
            print("new Name", new_name)
            try:
                projeto = Projeto.objects.get(nome=new_name)
            except Projeto.DoesNotExist:
                print(f"[ERRO] Projeto não encontrado: {new_name}")
                continue

            for email in entry["emails_abertura_st"]:
                email_obj, created = EmailAberturaST.objects.get_or_create(email=email)
                email_obj.projetos.add(projeto)  # associa o projeto ao email


def gerar_emails_list_by_farm():
    from .models import EmailAberturaST

    emails_dict = defaultdict(list)

    emails = EmailAberturaST.objects.prefetch_related("projetos").all()

    for email_obj in emails:
        projetos_nomes = sorted(
            [
                p.nome.replace("Projeto", "Fazenda").replace("Cacíque", "Cacique")
                for p in email_obj.projetos.all()
            ]
        )
        projetos_key = tuple(projetos_nomes)
        emails_dict[projetos_key].append(email_obj.email)

    emails_list_by_farm = []
    for projetos_key, emails in emails_dict.items():
        emails_list_by_farm.append(
            {
                "projetos": list(projetos_key),
                "emails_abertura_st": sorted(emails),
            }
        )

    return emails_list_by_farm


def get_emails_por_projeto(projeto):
    dados = gerar_emails_list_by_farm()
    emails = set()

    for item in dados:
        if projeto in item["projetos"]:
            emails.update(item["emails_abertura_st"])

    return sorted(list(emails))
