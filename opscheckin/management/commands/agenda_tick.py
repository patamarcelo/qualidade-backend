# opscheckin/management/commands/agenda_tick.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from opscheckin.models import  DailyCheckin, InboundMessage, OutboundMessage
from opscheckin.services.recipients import managers_subscribed
from opscheckin.services.whatsapp import send_list, send_buttons

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
    


def _wa_list_row_title(idx: int, text: str) -> str:
    """
    WhatsApp list row title: máximo 24 chars.
    Ex.: '✅ 3) Ajuste cronogr'
    """
    raw = f"✅ {idx}) {(text or '').strip()}"
    return raw[:24].rstrip()


def _wa_list_row_description(text: str) -> str:
    """
    Description pode ser maior; mantemos curta para leitura.
    """
    s = (text or "").strip()
    return (s[:72] + "…") if len(s) > 72 else s


def _agenda_reply_text(checkin):
    from opscheckin.models import AgendaItem

    items = AgendaItem.objects.filter(checkin=checkin).order_by("idx")
    if not items.exists():
        return "Ainda não tenho itens de agenda para hoje."

    lines = []
    for it in items:
        mark = "✅" if it.status == "done" else ("⛔" if it.status == "skip" else "⏳")
        lines.append(f"{mark} {it.idx}) {it.text}")

    return "Agenda de hoje:\n" + "\n".join(lines)



def _send_followup_buttons(manager, checkin):
    body = (
        "Atualização da agenda 🕘\n\n"
        f"{_agenda_reply_text(checkin)}\n\n"
        "Se quiser incluir um item, escreva:\n"
        "+ exemplo de item\n\n"
        "Ou, se deseja alterar alguma coisa na agenda,\n"
        "basta selecionar uma das opções abaixo:"
    )

    resp = send_buttons(
        manager.phone_e164,
        body=body,
        buttons=[
            {"id": "AM:MENU:DONE", "title": "✅ Concluir"},
            {"id": "AM:MENU:UNDO", "title": "↩️ Desmarcar"},
            {"id": "AM:MENU:REMOVE", "title": "🗑️ Remover"},
        ],
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

        qs = managers_subscribed(
            "agenda_followup",
            include_inactive=opts.get("include_inactive", False),
        )
        

        from opscheckin.models import AgendaItem

        sent = 0
        skipped = 0

        for m in qs:
            checkin = DailyCheckin.objects.filter(manager=m, date=day).first()
            if not checkin:
                logger.warning("AGENDA_FOLLOWUP_SKIP_NO_CHECKIN manager=%s day=%s", m.name, day)
                skipped += 1
                continue

            # precisa ter pelo menos 1 item de agenda no dia
            if not AgendaItem.objects.filter(checkin=checkin).exists():
                logger.warning(
                    "AGENDA_FOLLOWUP_SKIP_NO_ITEMS manager=%s checkin_id=%s",
                    m.name,
                    checkin.id,
                )
                skipped += 1
                continue

            # precisa ter agenda confirmada (manual ou auto)
            anchor = _agenda_confirm_anchor_at(checkin)
            if not anchor:
                logger.warning(
                    "AGENDA_FOLLOWUP_SKIP_NO_CONFIRM manager=%s checkin_id=%s",
                    m.name,
                    checkin.id,
                )
                skipped += 1
                continue

            # precisa ter itens abertos
            if not AgendaItem.objects.filter(checkin=checkin, status="open").exists():
                logger.warning(
                    "AGENDA_FOLLOWUP_SKIP_NO_OPEN_ITEMS manager=%s checkin_id=%s",
                    m.name,
                    checkin.id,
                )
                skipped += 1
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

            ok = _send_followup_buttons(m, checkin)
            if ok:
                sent += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[agenda_tick] managers={qs.count()} sent={sent} skipped={skipped}"
            )
        )