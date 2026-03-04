from datetime import datetime
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required

from .models import Manager, DailyCheckin, OutboundQuestion, InboundMessage, OutboundMessage
from .services.whatsapp import send_text
from .services.templates import render_message


DEFAULT_MSG = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)


def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _ticks_from_wa_status(wa_status: str):
    """
    Retorna (glyph, cssClass)
    """
    s = (wa_status or "").strip().lower()
    if s == "read":
        return ("✓✓", "ticksRead")
    if s == "delivered":
        return ("✓✓", "ticksDel")
    if s == "sent":
        return ("✓", "ticksSent")
    if s == "failed":
        return ("⚠", "ticksFail")
    return ("", "")


def _build_full_timeline(checkin):
    items = []

    # outbound
    for om in checkin.outbound_messages.all().order_by("sent_at", "id"):
        glyph, cls = _ticks_from_wa_status(getattr(om, "wa_status", ""))

        items.append({
            "ts": om.sent_at,
            "side": "right",
            "text": om.text,
            "is_outbound": True,
            "meta": om.kind,
            "ticks": glyph,
            "ticks_class": cls,
        })

    # inbound
    for im in checkin.inbound_messages.all().order_by("received_at", "id"):
        items.append({
            "ts": im.received_at,
            "side": "left",
            "text": im.text,
            "is_outbound": False,
            "meta": "",
            "ticks": "",
            "ticks_class": "",
        })

    items.sort(key=lambda x: x["ts"] or timezone.now())

    for it in items:
        ts = it["ts"] or timezone.now()
        it["label"] = timezone.localtime(ts).strftime("%H:%M")

    return items


@staff_member_required
@require_http_methods(["GET", "POST"])
def board_view(request):
    date_str = request.GET.get("date") or ""
    day = _parse_date(date_str) or timezone.localdate()

    managers = Manager.objects.all().order_by("name")

    # POST envio manual (massa OU por coluna)
    if request.method == "POST":
        now = timezone.now()

        mode = (request.POST.get("mode") or "").strip()  # "bulk" | "single"
        msg_bulk = (request.POST.get("message_bulk") or "").strip()
        msg_single = (request.POST.get("message_single") or "").strip()

        # fallback para evitar vazio
        if mode == "bulk":
            msg_tpl = msg_bulk or DEFAULT_MSG
            ids = request.POST.getlist("manager_ids")
            qs = managers.filter(id__in=ids) if ids else managers
        else:
            msg_tpl = msg_single or ""
            mid = (request.POST.get("manager_id") or "").strip()
            qs = managers.filter(id=mid) if mid else Manager.objects.none()

        for m in qs:
            checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=day)
            final_msg = render_message(msg_tpl, m)

            # opcional: manter um OutboundQuestion "MANUAL" (fica bom para auditoria)
            q = OutboundQuestion.objects.create(
                checkin=checkin,
                step="MANUAL",
                scheduled_for=now,
                sent_at=now,
                status="pending",
                prompt_text=final_msg,
            )

            # envia e captura wamid
            resp = None
            try:
                resp = send_text(m.phone_e164, final_msg)
            except Exception as e:
                # registra outbound failed mesmo assim
                OutboundMessage.objects.create(
                    manager=m,
                    checkin=checkin,
                    related_question=q,
                    to_phone=m.phone_e164,
                    provider_message_id="",
                    kind="manual",
                    text=final_msg,
                    sent_at=now,
                    raw_response={"error": str(e)},
                    wa_status="failed",
                )
                continue

            # extrai wamid
            wamid = ""
            try:
                wamid = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
            except Exception:
                wamid = ""

            data = dict(
                manager=m,
                checkin=checkin,
                related_question=q,
                to_phone=m.phone_e164,
                provider_message_id=wamid,
                kind="manual",
                text=final_msg,
                sent_at=now,
                raw_response=resp,
            )

            if wamid:
                data["wa_status"] = "sent"
                data["wa_sent_at"] = now

            OutboundMessage.objects.create(**data)

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
            cols.append({"manager": m, "timeline": [], "agenda_q": None})
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
        "status_filter": request.GET.get("status") or "",
    })