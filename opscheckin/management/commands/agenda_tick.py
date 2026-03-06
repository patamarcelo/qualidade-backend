# opscheckin/management/commands/agenda_tick.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from opscheckin.models import Manager, DailyCheckin, InboundMessage, OutboundMessage
from opscheckin.services.whatsapp import send_list

logger = logging.getLogger("opscheckin.agenda_tick")

# 90 em 90 minutos (real)
FOLLOWUP_EVERY_MINUTES = 90

# janela operacional (local)
START_HOUR = 9
END_HOUR = 17  # inclusive (vamos permitir até 17:59)

# anti-spam
COOLDOWN_MINUTES = 35  # não manda se houve atividade recente

# limite do WhatsApp na list (rows) — costuma ser 10 por seção; dependendo conta pode aceitar mais,
# mas vamos ser conservadores:
MAX_ROWS = 10


def _local_today():
    return timezone.localdate()


def _in_operational_window(local_now):
    # permite de START_HOUR:00 até END_HOUR:59
    return START_HOUR <= local_now.hour <= END_HOUR


def _recent_activity_at(manager, checkin):
    """
    Última atividade inbound/outbound (qualquer kind) para evitar spam.
    """
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


def _last_followup_sent_at(checkin):
    """
    Âncora do 90/90: último outbound do tipo agenda_followup.
    """
    return (
        OutboundMessage.objects
        .filter(checkin=checkin, kind="agenda_followup")
        .order_by("-sent_at", "-id")
        .values_list("sent_at", flat=True)
        .first()
    )


def _agenda_confirm_anchor_at(checkin):
    """
    O 90/90 só começa depois que a confirmação foi respondida (manual ou auto).
    Usa answered_at do OutboundQuestion AGENDA_CONFIRM.
    """
    q = (
        checkin.questions
        .filter(step="AGENDA_CONFIRM")
        .order_by("-id")
        .first()
    )
    if not q:
        return None
    if q.status != "answered":
        return None
    return q.answered_at or q.sent_at  # fallback


def _log_outbound_interactive(*, manager, checkin, body, resp, kind="agenda_followup"):
    now = timezone.now()
    provider_id = ""
    try:
        provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        pass

    data = dict(
        manager=manager,
        checkin=checkin,
        related_question=None,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=body,
        sent_at=now,
        raw_response=resp,
    )
    if provider_id:
        data["wa_status"] = "sent"
        data["wa_sent_at"] = now

    OutboundMessage.objects.create(**data)


def _send_followup_list(manager, checkin):
    from opscheckin.models import AgendaItem

    open_items = list(
        AgendaItem.objects.filter(checkin=checkin, status="open")
        .order_by("idx")[:MAX_ROWS]
    )
    if not open_items:
        return False

    body = (
        "Atualização da agenda 🕘\n\n"
        "Algum item foi concluído?\n"
        "Selecione abaixo o que foi feito:"
    )

    sections = [
        {
            "title": "Marcar como concluído",
            "rows": [
                {
                    "id": f"AP:DONE:{it.id}",
                    "title": f"✅ {it.idx}) {it.text[:60]}",
                    "description": (it.text[:60] + "…") if len(it.text) > 60 else it.text,
                }
                for it in open_items
            ],
        }
    ]

    resp = send_list(
        manager.phone_e164,
        body=body,
        button_text="Selecionar item",
        sections=sections,
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=checkin,
        body=body,
        resp=resp,
        kind="agenda_followup",
    )
    return True


class Command(BaseCommand):
    help = "Follow-up real 90/90 (relativo) após confirmação da agenda, com Interactive List."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true")
        parser.add_argument("--every-min", type=int, default=FOLLOWUP_EVERY_MINUTES)
        parser.add_argument("--cooldown-min", type=int, default=COOLDOWN_MINUTES)

    def handle(self, *args, **opts):
        now = timezone.now()
        local_now = timezone.localtime(now)

        day = _local_today()
        if opts["date"]:
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        every_min = int(opts["every_min"] or FOLLOWUP_EVERY_MINUTES)
        cooldown_min = int(opts["cooldown_min"] or COOLDOWN_MINUTES)

        # só roda no horário operacional (evita followup às 3 da manhã caso scheduler rode)
        if not _in_operational_window(local_now):
            self.stdout.write("[agenda_tick] out of operational window")
            return

        qs = Manager.objects.all().order_by("name")
        if not opts.get("include_inactive", False):
            qs = qs.filter(is_active=True)

        from opscheckin.models import AgendaItem

        sent = 0
        skipped = 0

        for m in qs:
            checkin = DailyCheckin.objects.filter(manager=m, date=day).first()
            if not checkin:
                continue

            # precisa ter agenda confirmada (manual ou auto)
            anchor = _agenda_confirm_anchor_at(checkin)
            if not anchor:
                continue

            # precisa ter itens abertos
            if not AgendaItem.objects.filter(checkin=checkin, status="open").exists():
                continue

            # cooldown por atividade recente
            last_activity = _recent_activity_at(m, checkin)
            if last_activity:
                age_min = (now - last_activity).total_seconds() / 60.0
                if age_min < cooldown_min:
                    logger.warning(
                        "AGENDA_FOLLOWUP_SKIP_COOLDOWN manager=%s age_min=%.1f",
                        m.name, age_min
                    )
                    skipped += 1
                    continue

            # âncora 90/90: último followup, senão a confirmação
            last_fu = _last_followup_sent_at(checkin)
            base = last_fu or anchor

            due_at = base + timedelta(minutes=every_min)
            if now < due_at:
                continue

            ok = _send_followup_list(m, checkin)
            if ok:
                sent += 1

        self.stdout.write(self.style.SUCCESS(f"[agenda_tick] sent={sent} skipped={skipped}"))