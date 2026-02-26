from django.utils import timezone


def render_message(template: str, manager) -> str:
    """
    Renderiza placeholders simples no template.
    Suportados:
    - {name}
    - {date}
    - {weekday}
    """
    today = timezone.localdate()

    context = {
        "name": manager.name or "",
        "date": today.strftime("%d/%m/%Y"),
        "weekday": today.strftime("%A"),
    }

    try:
        return template.format(**context)
    except Exception:
        # fallback seguro
        return template