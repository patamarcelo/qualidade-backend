from datetime import datetime
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.db.models import Prefetch

from .models import Manager, DailyCheckin, OutboundQuestion, InboundMessage
from .services.whatsapp import send_text
from .services.templates import render_message
from django.contrib.admin.views.decorators import staff_member_required


DEFAULT_MSG = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)


def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _build_full_timeline(checkin):
    items = []

    for om in checkin.outbound_messages.all():
        items.append({
            "ts": om.sent_at,
            "side": "right",
            "text": om.text,
            "is_outbound": True,
            "meta": om.kind,
        })

    for im in checkin.inbound_messages.all():
        items.append({
            "ts": im.received_at,
            "side": "left",
            "text": im.text,
            "is_outbound": False,
            "meta": "",
        })

    items.sort(key=lambda x: x["ts"] or timezone.now())

    for it in items:
        ts = it["ts"] or timezone.now()
        # ✅ converte para o timezone “corrente” do Django (settings.TIME_ZONE ou ativado)
        it["label"] = timezone.localtime(ts).strftime("%H:%M")

    return items


@staff_member_required
@require_http_methods(["GET", "POST"])
def board_view(request):

    date_str = request.GET.get("date") or ""
    day = _parse_date(date_str) or timezone.localdate()

    managers = Manager.objects.all().order_by("name")

    # POST envio manual
    if request.method == "POST":
        msg = (request.POST.get("message") or "").strip() or DEFAULT_MSG
        ids = request.POST.getlist("manager_ids")
        now = timezone.now()

        qs = managers.filter(id__in=ids) if ids else managers

        for m in qs:
            checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=day)

            final_msg = render_message(msg, m)

            q = OutboundQuestion.objects.create(
                checkin=checkin,
                step="MANUAL",
                scheduled_for=now,
                sent_at=now,
                status="pending",
                prompt_text=final_msg,
            )

            send_text(m.phone_e164, final_msg)

        return redirect(f"{request.path}?date={day.isoformat()}")

    # Pré-carrega tudo
    checkins = (
        DailyCheckin.objects
        .filter(date=day)
        .select_related("manager")
        .prefetch_related("questions", "inbound_messages", "outbound_messages")
    )

    by_manager = {c.manager_id: c for c in checkins}

    cols = []

    for m in managers:
        c = by_manager.get(m.id)

        if not c:
            cols.append({
                "manager": m,
                "timeline": [],
                "agenda_q": None,
            })
            continue

        timeline = _build_full_timeline(c)

        agenda_q = c.questions.filter(step="AGENDA").order_by("-id").first()

        cols.append({
            "manager": m,
            "timeline": timeline,
            "agenda_q": agenda_q,
        })

    return render(request, "opscheckin/board.html", {
        "day": day,
        "cols": cols,
        "managers": list(managers),
        "default_msg": DEFAULT_MSG,
    })