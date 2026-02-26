from datetime import datetime
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Manager, DailyCheckin, OutboundQuestion, InboundMessage
from .services.whatsapp import send_text
from opscheckin.services.templates import render_message

DEFAULT_MSG = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)

def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _build_timeline(checkin):
    """
    Timeline simples:
    - pergunta AGENDA (se enviada) à direita
    - inbounds linkados a ela à esquerda
    """
    items = []

    q = (
        checkin.questions
        .filter(step="AGENDA")
        .order_by("scheduled_for", "id")
        .first()
    )

    if q and q.sent_at:
        items.append({
            "ts": q.sent_at,
            "side": "right",
            "label": f"{q.step} • {q.sent_at.astimezone().strftime('%H:%M')}",
            "text": DEFAULT_MSG,
            "meta": f"status: {q.status}",
        })

        inbs = (
            checkin.inbound_messages
            .filter(linked_question=q)
            .order_by("received_at", "id")
        )
        for im in inbs:
            items.append({
                "ts": im.received_at,
                "side": "left",
                "label": im.received_at.astimezone().strftime("%H:%M"),
                "text": im.text,
                "meta": "",
            })

    return items, q

@require_http_methods(["GET", "POST"])
def board_view(request):
    # filtro por data
    date_str = request.GET.get("date") or ""
    day = _parse_date(date_str) or timezone.localdate()

    managers = Manager.objects.filter(is_active=True).order_by("name")

    # envio manual
    if request.method == "POST":
        msg = (request.POST.get("message") or "").strip() or DEFAULT_MSG
        ids = request.POST.getlist("manager_ids")  # múltiplos

        qs = managers.filter(id__in=ids) if ids else managers  # se nada marcado, envia para todos
        now = timezone.now()

        for m in qs:
            checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=day)
            q = OutboundQuestion.objects.create(
                checkin=checkin,
                step="MANUAL",
                scheduled_for=now,
                sent_at=now,
                status="pending",
            )

            final_msg = render_message(msg, m)
            send_text(m.phone_e164, final_msg)
        return redirect(f"{request.path}?date={day.isoformat()}")

    # carrega checkins do dia
    checkins = (
        DailyCheckin.objects
        .select_related("manager")
        .prefetch_related("questions", "inbound_messages")
        .filter(date=day, manager__is_active=True)
    )
    by_manager_id = {c.manager_id: c for c in checkins}

    cols = []
    for m in managers:
        c = by_manager_id.get(m.id)
        if not c:
            cols.append({"manager": m, "checkin": None, "timeline": [], "agenda_q": None})
            continue

        timeline, agenda_q = _build_timeline(c)

        cols.append({
            "manager": m,
            "checkin": c,
            "timeline": timeline,
            "agenda_q": agenda_q,
        })

    return render(request, "opscheckin/board.html", {
        "day": day,
        "cols": cols,
        "managers": list(managers),
        "default_msg": DEFAULT_MSG,
    })