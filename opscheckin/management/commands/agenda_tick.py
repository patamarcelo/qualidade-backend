from __future__ import annotations

import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from opscheckin.models import Manager, DailyCheckin, InboundMessage, OutboundMessage
from opscheckin.services.whatsapp import send_buttons

logger = logging.getLogger("opscheckin.agenda_tick")

# a cada 2h até 17:00 (hora local)
AGENDA_FOLLOWUP_SLOTS = [
    (9, 0),
    (11, 0),
    (13, 0),
    (15, 0),
    (17, 0),
]

SLOT_GRACE_SECONDS = 120
COOLDOWN_MINUTES = 35  # não manda se houve atividade recente


def _local_today():
    return timezone.localdate()


def _is_in_slot(local_now, hh, mm, grace_seconds=SLOT_GRACE_SECONDS):
    start = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    end = start + timezone.timedelta(seconds=grace_seconds)
    return start <= local_now < end


def _log_outbound_interactive(*, manager, checkin, body, resp):
    now = timezone.now()
    provider_id = ""
    try:
        provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        pass

    OutboundMessage.objects.create(
        manager=manager,
        checkin=checkin,
        related_question=None,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind="other",  # opcional: "agenda_item"
        text=body,
        sent_at=now,
        raw_response=resp,
    )


def _send_next_agenda_item_prompt(manager, checkin):
    from opscheckin.models import AgendaItem

    it = (
        AgendaItem.objects.filter(checkin=checkin, status="open")
        .order_by("idx")
        .first()
    )
    if not it:
        return False

    body = f"Item {it.idx}:\n{it.text}\n\nStatus?"
    resp = send_buttons(
        manager.phone_e164,
        body=body,
        buttons=[
            {"id": f"AI:{it.id}:done", "title": "✅ Feito"},
            {"id": f"AI:{it.id}:open", "title": "⏳ Ainda não"},
            {"id": f"AI:{it.id}:skip", "title": "⛔ Pular"},
        ],
    )

    _log_outbound_interactive(manager=manager, checkin=checkin, body=body, resp=resp)
    return True


def _recent_activity_at(manager, checkin):
    last_in = (
        InboundMessage.objects
        .filter(Q(manager=manager) | Q(from_phone=manager.phone_e164))
        .order_by("-received_at")
        .values_list("received_at", flat=True)
        .first()
    )
    last_out = (
        OutboundMessage.objects
        .filter(checkin=checkin)
        .order_by("-sent_at")
        .values_list("sent_at", flat=True)
        .first()
    )
    candidates = [x for x in (last_in, last_out) if x]
    return max(candidates) if candidates else None


class Command(BaseCommand):
    help = "Follow-up de AgendaItems (slots fixos a cada 2h) com botões interativos."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true")

    def handle(self, *args, **opts):
        now = timezone.now()
        local_now = timezone.localtime(now)

        day = _local_today()
        if opts["date"]:
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        # só roda se estamos em algum slot
        in_slot = any(_is_in_slot(local_now, hh, mm) for (hh, mm) in AGENDA_FOLLOWUP_SLOTS)
        if not in_slot:
            self.stdout.write("[agenda_tick] not in slot")
            return

        qs = Manager.objects.all().order_by("name")
        if not opts["include-inactive"]:
            qs = qs.filter(is_active=True)

        from opscheckin.models import AgendaItem

        for m in qs:
            checkin = DailyCheckin.objects.filter(manager=m, date=day).first()
            if not checkin:
                continue

            if not AgendaItem.objects.filter(checkin=checkin, status="open").exists():
                continue

            last_activity = _recent_activity_at(m, checkin)
            if last_activity:
                age_min = (now - last_activity).total_seconds() / 60.0
                if age_min < COOLDOWN_MINUTES:
                    logger.warning(
                        "AGENDA_FOLLOWUP_SKIP_COOLDOWN manager=%s age_min=%.1f",
                        m.name, age_min
                    )
                    continue

            _send_next_agenda_item_prompt(m, checkin)

        self.stdout.write(self.style.SUCCESS("[agenda_tick] done"))