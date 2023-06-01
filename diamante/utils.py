from datetime import timedelta
import datetime

today = datetime.date.today()


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
