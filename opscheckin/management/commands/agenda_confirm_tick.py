# opscheckin/management/commands/agenda_confirm_tick.py
from __future__ import annotations

import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import Manager, DailyCheckin, OutboundQuestion, OutboundMessage
from opscheckin.services.whatsapp import send_list

logger = logging.getLogger("opscheckin.agenda_confirm_tick")

# fluxo
SEND_CONFIRM_AFTER_MINUTES = 10
AUTO_OK_MINUTES = 15

SLOT_GRACE_SECONDS = 120
CHECK_EVERY_MINUTE_MODE = True  # roda via cron a cada 1-2 min

# ids do fluxo (webhook precisa entender)
# - AC:OK
# - AC:RM:<agenda_item_id>

def _local_today():
    return timezone.localdate()


def _log_outbound_interactive(*, manager, checkin, body, resp, kind="agenda_confirm"):
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
        kind=kind,
        text=body,
        sent_at=now,
        raw_response=resp,
        wa_status=("sent" if provider_id else ""),
        wa_sent_at=(now if provider_id else None),
    )


def _agenda_preview(checkin, *, max_lines=12) -> str:
    from opscheckin.models import AgendaItem
    items = list(AgendaItem.objects.filter(checkin=checkin).order_by("idx")[:max_lines])
    if not items:
        return "(sem itens)"
    lines = []
    for it in items:
        lines.append(f"{it.idx}) {it.text}")
    if len(items) >= max_lines:
        lines.append("…")
    return "\n".join(lines)


def _ensure_confirm_question(checkin, *, now):
    """
    Garante OutboundQuestion step=AGENDA_CONFIRM para auditoria e auto-ok.
    """
    q = (
        checkin.questions
        .filter(step="AGENDA_CONFIRM")
        .order_by("-scheduled_for", "-id")
        .first()
    )
    if q and q.sent_at:
        return q

    q = OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA_CONFIRM",
        scheduled_for=now,
        status="pending",
        prompt_text="AGENDA_CONFIRM",
    )
    return q


def _send_confirm(manager, checkin):
    from opscheckin.models import AgendaItem

    items = list(AgendaItem.objects.filter(checkin=checkin).order_by("idx"))
    if not items:
        return False

    preview = _agenda_preview(checkin)

    body = (
        "Recebi sua agenda ✅\n\n"
        "Prévia:\n"
        f"{preview}\n\n"
        "Quer remover algum item ou está OK?\n"
        "• Se quiser adicionar: envie + texto"
    )

    sections = [
        {
            "title": "Está OK",
            "rows": [
                {"id": "AC:OK", "title": "✅ OK (manter agenda)", "description": "Confirma sem remover itens"},
            ],
        },
        {
            "title": "Remover item",
            "rows": [
                {
                    "id": f"AC:RM:{it.id}",
                    "title": f"⛔ Remover {it.idx})",
                    "description": (it.text[:60] + "…") if len(it.text) > 60 else it.text,
                }
                for it in items[:20]  # limite do WhatsApp; se passar, a gente pagina depois
            ],
        },
    ]

    resp = send_list(
        manager.phone_e164,
        body=body,
        button_text="Abrir opções",
        sections=sections,
    )
    _log_outbound_interactive(manager=manager, checkin=checkin, body=body, resp=resp, kind="agenda_confirm")
    return True


class Command(BaseCommand):
    help = "Envia confirmação da agenda (10 min após resposta) e aplica OK automático por silêncio."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true")
        parser.add_argument("--send-after-min", type=int, default=SEND_CONFIRM_AFTER_MINUTES)
        parser.add_argument("--auto-ok-min", type=int, default=AUTO_OK_MINUTES)

    def handle(self, *args, **opts):
        now = timezone.now()
        day = _local_today()
        if opts["date"]:
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        send_after = int(opts["send_after_min"] or SEND_CONFIRM_AFTER_MINUTES)
        auto_ok_min = int(opts["auto_ok_min"] or AUTO_OK_MINUTES)

        qs = Manager.objects.all().order_by("name")
        if not opts["include-inactive"]:
            qs = qs.filter(is_active=True)

        sent = 0
        auto_ok = 0

        for m in qs:
            checkin = DailyCheckin.objects.filter(manager=m, date=day).first()
            if not checkin:
                continue

            agenda_q = (
                checkin.questions.filter(step="AGENDA")
                .order_by("-id")
                .first()
            )
            if not agenda_q or agenda_q.status != "answered" or not agenda_q.answered_at:
                continue

            # se ainda não passou 10 min desde resposta da agenda, não manda confirmação
            age_min = (now - agenda_q.answered_at).total_seconds() / 60.0
            if age_min < send_after:
                continue

            # 1) cria/manda confirmação se ainda não foi enviada
            conf_q = (
                checkin.questions.filter(step="AGENDA_CONFIRM")
                .order_by("-id")
                .first()
            )

            if not conf_q or not conf_q.sent_at:
                conf_q = _ensure_confirm_question(checkin, now=now)
                ok = _send_confirm(m, checkin)
                if ok:
                    conf_q.sent_at = now
                    conf_q.save(update_fields=["sent_at"])
                    sent += 1
                continue

            # 2) auto-ok: se confirmação está pending e já passou auto_ok_min desde envio
            if conf_q.status == "pending" and conf_q.sent_at and not conf_q.answered_at:
                conf_age = (now - conf_q.sent_at).total_seconds() / 60.0
                if conf_age >= auto_ok_min:
                    conf_q.status = "answered"
                    conf_q.answered_at = now
                    conf_q.answer_text = "ok (auto)"
                    conf_q.save(update_fields=["status", "answered_at", "answer_text"])
                    auto_ok += 1

        self.stdout.write(self.style.SUCCESS(f"[agenda_confirm_tick] sent={sent} auto_ok={auto_ok}"))