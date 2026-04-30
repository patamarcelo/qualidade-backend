from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from opscheckin.models import OpsBoardAccess


def _safe_reverse(name, fallback):
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback


def ops_dashboard_cards(request):
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {"ops_dashboard_cards": []}

    cards = []

    board_url = _safe_reverse("opscheckin_board", "/opscheckin/board/")

    if user.is_superuser:
        cards.append({
            "title": "Board WhatsApp",
            "subtitle": "Visualização global de conversas, respostas e envios via template.",
            "url": board_url,
            "icon": "💬",
            "badge": "Global",
            "theme": "green",
        })

    else:
        access = (
            OpsBoardAccess.objects
            .select_related("coordinator")
            .filter(
                user=user,
                is_active=True,
                coordinator__is_personal_reminder_coordinator=True,
            )
            .first()
        )

        if access:
            cards.append({
                "title": "Board WhatsApp",
                "subtitle": f"Conversas dos managers sob gestão de {access.coordinator.name}.",
                "url": board_url,
                "icon": "💬",
                "badge": "Coordenação",
                "theme": "blue",
            })

    return {"ops_dashboard_cards": cards}