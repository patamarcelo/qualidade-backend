from datetime import timedelta
import datetime


today = datetime.date.today()

import requests
import json

from qualidade_project.settings import FARMBOX_ID


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


def admin_form_alter_programa_and_save(
    query, operation, current_op_products, difDap, newDap
):
    for i in query:
        try:
            index = get_index_dict_estagio(i.cronograma_programa, operation)
            print("Index: ", index)
            if index:
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
                    i.save()
                    print(f"Alteração de programa salva com sucesso: {i}")
            else:
                operation_to_add = {
                    "dap": newDap,
                    "estagio": operation,
                    "aplicado": False,
                    "produtos": current_op_products,
                    "data prevista": format_date_json(
                        get_prev_app_date(i.data_plantio, newDap)
                    ),
                }
                i.cronograma_programa.append(operation_to_add)
                i.save()
                print(f"Estágio incluído com sucesso: {i}")
        except Exception as e:
            print("Erro ao Salvar a alteração no programa do  plantio", e)


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
    return response


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
