from django import template
from datetime import datetime


register = template.Library()

@register.filter
def formatar_numero_br(value, decimal_places=2):
    print('formatar numero')
    print(value)
    print(type(value))
    try:
        number = float(value)
    except (ValueError, TypeError):
        return value

    inteiro, decimal = f"{number:.{decimal_places}f}".split(".")
    inteiro_formatado = f"{int(inteiro):,}".replace(",", ".")
    numero_formatado = f"{inteiro_formatado},{decimal}"
    print('numero formatado: ', numero_formatado)
    return numero_formatado

@register.filter
def formatar_data_brasileira(data_str):
    """
    Recebe uma string no formato ISO 'YYYY-MM-DD' e retorna no formato brasileiro 'DD/MM/YYYY'.
    Se a entrada for None ou inválida, retorna uma string vazia.
    """
    if not data_str:
        return ""
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d")
        return data_obj.strftime("%d/%m/%Y")
    except ValueError:
        return ""

@register.filter
def format_farm_name(farm):
    """Remove a palavra 'Fazenda' de um nome de fazenda"""
    if farm:
        return farm.replace('Fazenda', '').strip()
    return ''