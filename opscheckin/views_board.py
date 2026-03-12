from datetime import datetime, time

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    DailyCheckin,
    InboundMessage,
    Manager,
    OutboundMessage,
    OutboundQuestion,
)
from .services.templates import render_message
from .services.whatsapp import send_text

from django.http import JsonResponse
from django.utils.dateparse import parse_datetime


DEFAULT_MSG = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)

def _iso(dt):
    if not dt:
        return ""
    return timezone.localtime(dt).isoformat()


def _parse_since(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _build_message_payload(it):
    return {
        "message_id": it.get("message_id", ""),
        "provider_message_id": it.get("provider_message_id", ""),
        "manager_id": it["manager_id"],
        "column_id": f"manager-{it['manager_id']}",
        "kind": it["kind"],
        "ts": _iso(it["ts"]),
        "label": timezone.localtime(it["ts"]).strftime("%H:%M") if it.get("ts") else "",
        "side": it["side"],
        "text": it["text"] or "",
        "meta": it.get("meta", "") or "",
        "ticks": it.get("ticks", "") or "",
        "ticks_class": it.get("ticks_class", "") or "",
    }


@staff_member_required
@require_http_methods(["GET"])
def board_updates(request):
    day_str = request.GET.get("day") or ""
    since_str = request.GET.get("since") or ""

    day = _parse_date(day_str) or timezone.localdate()
    start_dt, end_dt = _day_bounds_local(day)
    since = _parse_since(since_str) or start_dt

    managers = list(Manager.objects.all().order_by("name"))
    manager_ids = [m.id for m in managers]

    outbound_qs = (
        OutboundMessage.objects
        .filter(
            manager_id__in=manager_ids,
            sent_at__gte=start_dt,
            sent_at__lte=end_dt,
            sent_at__gt=since,
        )
        .select_related("manager")
        .order_by("sent_at", "id")
    )

    inbound_qs = (
        InboundMessage.objects
        .filter(
            manager_id__in=manager_ids,
            received_at__gte=start_dt,
            received_at__lte=end_dt,
            received_at__gt=since,
        )
        .select_related("manager")
        .order_by("received_at", "id")
    )

    messages = []

    for om in outbound_qs:
        glyph, cls = _ticks_from_wa_status(getattr(om, "wa_status", ""))
        messages.append(_build_message_payload({
            "message_id": f"out-{om.id}",
            "provider_message_id": om.provider_message_id or "",
            "manager_id": om.manager_id,
            "kind": "outbound",
            "ts": om.sent_at,
            "side": "right",
            "text": om.text,
            "meta": om.kind or "",
            "ticks": glyph,
            "ticks_class": cls,
        }))

    for im in inbound_qs:
        messages.append(_build_message_payload({
            "message_id": f"in-{im.id}",
            "provider_message_id": "",
            "manager_id": im.manager_id,
            "kind": "inbound",
            "ts": im.received_at,
            "side": "left",
            "text": im.text,
            "meta": im.msg_type or "",
        }))

    messages.sort(key=lambda x: x["ts"] or "")

    checkins = (
        DailyCheckin.objects
        .filter(date=day, manager_id__in=manager_ids)
        .prefetch_related("questions")
    )
    by_manager = {c.manager_id: c for c in checkins}

    try:
        from .models import AgendaItem

        item_stats = (
            AgendaItem.objects.filter(checkin__date=day, checkin__manager_id__in=manager_ids)
            .values("checkin__manager_id")
            .annotate(
                total=Count("id"),
                open=Count("id", filter=Q(status="open")),
                done=Count("id", filter=Q(status="done")),
                skip=Count("id", filter=Q(status="skip")),
            )
        )
        stats_by_manager = {x["checkin__manager_id"]: x for x in item_stats}
    except Exception:
        stats_by_manager = {}

    manager_updates = []
    for m in managers:
        c = by_manager.get(m.id)
        agenda_q = c.questions.filter(step="AGENDA").order_by("-id").first() if c else None
        confirm_q = c.questions.filter(step="AGENDA_CONFIRM").order_by("-id").first() if c else None
        st = stats_by_manager.get(m.id) or {}

        timeline = _build_manager_timeline(m, start_dt, end_dt)
        preview = _build_sidebar_preview(timeline)

        manager_updates.append({
            "manager_id": m.id,
            "column_id": f"manager-{m.id}",
            "last_ts": _iso(preview["last_ts"]) if preview["last_ts"] else "",
            "last_label": preview["last_label"],
            "last_preview": preview["last_preview"],
            "last_side": preview["last_side"],
            "agenda_badge": list(_badge_for_q(agenda_q)),
            "confirm_badge": list(_badge_for_q(confirm_q)),
            "items": {
                "total": int(st.get("total") or 0),
                "open": int(st.get("open") or 0),
                "done": int(st.get("done") or 0),
                "skip": int(st.get("skip") or 0),
            },
        })

    latest_ts = []
    if messages:
        latest_ts.extend([parse_datetime(m["ts"]) for m in messages if m.get("ts")])

    server_now = timezone.now()
    max_ts = max(latest_ts) if latest_ts else server_now

    return JsonResponse({
        "ok": True,
        "day": day.isoformat(),
        "server_now": _iso(max_ts),
        "messages": messages,
        "manager_updates": manager_updates,
    })


def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def only_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def format_phone_br(phone: str) -> str:
    s = only_digits(phone)

    if not s:
        return "-"

    if s.startswith("55"):
        s = s[2:]

    if len(s) < 10:
        return phone or "-"

    ddd = s[:2]
    number = s[2:]

    if len(number) == 8:
        return f"({ddd}) {number[:4]}-{number[4:]}"
    if len(number) == 9:
        return f"({ddd}) {number[:5]}-{number[5:]}"

    return f"({ddd}) {number}"


def _ticks_from_wa_status(wa_status: str):
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


def _truncate(text: str, limit: int = 72) -> str:
    text = (text or "").strip().replace("\r", "")
    text = " ".join(text.splitlines()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _day_bounds_local(day):
    tz = timezone.get_current_timezone()
    start_local = timezone.make_aware(datetime.combine(day, time.min), tz)
    end_local = timezone.make_aware(datetime.combine(day, time.max), tz)
    return start_local, end_local


def _build_manager_timeline(manager, start_dt, end_dt):
    items = []

    outbound_qs = (
        OutboundMessage.objects
        .filter(
            manager=manager,
            sent_at__gte=start_dt,
            sent_at__lte=end_dt,
        )
        .order_by("sent_at", "id")
    )

    inbound_qs = (
        InboundMessage.objects
        .filter(
            manager=manager,
            received_at__gte=start_dt,
            received_at__lte=end_dt,
        )
        .order_by("received_at", "id")
    )

    for om in outbound_qs:
        glyph, cls = _ticks_from_wa_status(getattr(om, "wa_status", ""))

        items.append(
            {
                "ts": om.sent_at,
                "side": "right",
                "text": om.text,
                "is_outbound": True,
                "meta": (om.kind or ""),
                "ticks": glyph,
                "ticks_class": cls,
            }
        )

    for im in inbound_qs:
        items.append(
            {
                "ts": im.received_at,
                "side": "left",
                "text": im.text,
                "is_outbound": False,
                "meta": (im.msg_type or ""),
                "ticks": "",
                "ticks_class": "",
            }
        )

    items.sort(key=lambda x: x["ts"] or timezone.now())

    for it in items:
        ts = it["ts"] or timezone.now()
        it["label"] = timezone.localtime(ts).strftime("%H:%M")
        it["day_label"] = timezone.localtime(ts).strftime("%d/%m %H:%M")

    return items


def _badge_for_q(q):
    if not q:
        return ("—", "badge")
    s = (q.status or "").strip().lower()
    if s == "answered":
        at = (q.answer_text or "").lower()
        if "auto" in at:
            return ("answered(auto)", "badge b-ok")
        return ("answered", "badge b-ok")
    if s == "missed":
        return ("missed", "badge b-danger")
    return ("pending", "badge b-warn")


def _build_sidebar_preview(timeline):
    if not timeline:
        return {
            "last_ts": None,
            "last_label": "—",
            "last_preview": "Sem conversa ainda.",
            "last_side": "",
        }

    last = timeline[-1]
    ts = last.get("ts")
    return {
        "last_ts": ts,
        "last_label": timezone.localtime(ts).strftime("%H:%M") if ts else "—",
        "last_preview": _truncate(last.get("text") or ""),
        "last_side": "Você: " if last.get("is_outbound") else "",
    }


@staff_member_required
@require_http_methods(["GET", "POST"])
def board_view(request):
    date_str = request.GET.get("date") or ""
    day = _parse_date(date_str) or timezone.localdate()
    start_dt, end_dt = _day_bounds_local(day)

    managers = Manager.objects.all().order_by("name")

    if request.method == "POST":
        now = timezone.now()

        mode = (request.POST.get("mode") or "").strip()  # bulk | single
        msg_bulk = (request.POST.get("message_bulk") or "").strip()
        msg_single = (request.POST.get("message_single") or "").strip()

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

            q = OutboundQuestion.objects.create(
                checkin=checkin,
                step="MANUAL",
                scheduled_for=now,
                sent_at=now,
                status="pending",
                prompt_text=final_msg,
            )

            resp = None
            try:
                resp = send_text(m.phone_e164, final_msg)
            except Exception as e:
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

    checkins = (
        DailyCheckin.objects.filter(date=day)
        .select_related("manager")
        .prefetch_related("questions")
    )
    by_manager = {c.manager_id: c for c in checkins}

    try:
        from .models import AgendaItem

        item_stats = (
            AgendaItem.objects.filter(checkin__date=day)
            .values("checkin_id")
            .annotate(
                total=Count("id"),
                open=Count("id", filter=Q(status="open")),
                done=Count("id", filter=Q(status="done")),
                skip=Count("id", filter=Q(status="skip")),
            )
        )
        stats_by_checkin = {x["checkin_id"]: x for x in item_stats}
    except Exception:
        stats_by_checkin = {}

    cols = []
    for m in managers:
        c = by_manager.get(m.id)

        timeline = _build_manager_timeline(m, start_dt, end_dt)

        if not c:
            cols.append(
                {
                    "manager": m,
                    "manager_phone_display": format_phone_br(m.phone_e164),
                    "timeline": timeline,
                    "agenda_q": None,
                    "confirm_q": None,
                    "agenda_badge": ("—", "badge"),
                    "confirm_badge": ("—", "badge"),
                    "items": {"total": 0, "open": 0, "done": 0, "skip": 0},
                    "column_id": f"manager-{m.id}",
                    **_build_sidebar_preview(timeline),
                }
            )
            continue

        agenda_q = c.questions.filter(step="AGENDA").order_by("-id").first()
        confirm_q = c.questions.filter(step="AGENDA_CONFIRM").order_by("-id").first()

        agenda_badge = _badge_for_q(agenda_q)
        confirm_badge = _badge_for_q(confirm_q)

        st = stats_by_checkin.get(c.id) or {}
        items = {
            "total": int(st.get("total") or 0),
            "open": int(st.get("open") or 0),
            "done": int(st.get("done") or 0),
            "skip": int(st.get("skip") or 0),
        }

        cols.append(
            {
                "manager": m,
                "manager_phone_display": format_phone_br(m.phone_e164),
                "timeline": timeline,
                "agenda_q": agenda_q,
                "confirm_q": confirm_q,
                "agenda_badge": agenda_badge,
                "confirm_badge": confirm_badge,
                "items": items,
                "column_id": f"manager-{m.id}",
                **_build_sidebar_preview(timeline),
            }
        )

    cols.sort(
        key=lambda x: (
            0 if x["last_ts"] else 1,
            -(x["last_ts"].timestamp()) if x["last_ts"] else 0,
            (x["manager"].name or "").lower(),
        )
    )

    return render(
        request,
        "opscheckin/board.html",
        {
            "day": day,
            "cols": cols,
            "managers": list(managers),
            "default_msg": DEFAULT_MSG,
            "status_filter": request.GET.get("status") or "",
            "initial_sync": timezone.now().isoformat(),
        },
    )