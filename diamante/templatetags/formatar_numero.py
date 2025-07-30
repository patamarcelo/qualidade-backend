from django import template

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