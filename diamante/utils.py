from datetime import timedelta
import datetime


today = datetime.date.today()


# pr_mungo = Programa.objects.all()[2]
# pr_caupi = Programa.objects.all()[1]
# pr_rr = Programa.objects.all()[4]
# pr_conven = Programa.objects.all()[3]

# pl_rr = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Soja", finalizado_plantio=True).filter(programa=pr_rr)
# pl_conv = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Soja", finalizado_plantio=True).filter(programa=pr_conven)
# pl_caupi = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Feijão", finalizado_plantio=True).filter(programa=pr_caupi)
# pl_mungo = Plantio.objects.filter(safra__safra="2023/2024", ciclo__ciclo="1", variedade__cultura__cultura="Feijão", finalizado_plantio=True).filter(programa=pr_mungo)


def get_dap(data_plantio):
    dap = 0
    today = datetime.date.today()
    if data_plantio:
        dap = today - data_plantio
        dap = dap.days + 1
    return dap


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


v6_1_conv = {
    "dap": 40,
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
            "dose": "0.040",
            "tipo": "inseticida",
            "produto": "Bifentrina",
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
    ],
    "data prevista": "",
}
v6_2_conv = {
    "dap": 40,
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
            "dose": "0.200",
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
            "dose": "0.040",
            "tipo": "inseticida",
            "produto": "Bifentrina",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.150",
            "tipo": "inseticida",
            "produto": "Lambda",
            "quantidade aplicar": "",
        },
        {
            "dose": "0.022",
            "tipo": "inseticida",
            "produto": "ABAMECTINA 400",
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
            "dose": "0.200",
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
