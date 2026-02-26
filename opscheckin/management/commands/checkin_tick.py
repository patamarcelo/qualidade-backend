# opscheckin/management/commands/checkin_tick.py
from __future__ import annotations

from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import Manager, DailyCheckin, OutboundQuestion, OutboundMessage
from opscheckin.services.whatsapp import send_text


DEFAULT_AGENDA_TEMPLATE = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)

DEFAULT_REMINDER_TEXT = "??"


def _local_today():
    # timezone do Django deve estar configurada p/ America/Sao_Paulo
    return timezone.localdate()


def _ensure_checkin(manager: Manager, day):
    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=day)
    return checkin


def _log_outbound(*, manager: Manager, checkin: DailyCheckin, related_question: OutboundQuestion | None, kind: str, text: str, now, resp: dict | None):
    """
    Cria log do que foi ENVIADO para o WhatsApp (espelho do InboundMessage).
    """
    provider_id = ""
    try:
        provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        provider_id = ""

    OutboundMessage.objects.create(
        manager=manager,
        checkin=checkin,
        related_question=related_question,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=text,
        sent_at=now,
        raw_response=resp,
    )


def _send_agenda_if_needed(
    *,
    manager: Manager,
    checkin: DailyCheckin,
    now,
    agenda_text: str,
):
    """
    Garante que existe UMA pergunta AGENDA enviada hoje.
    Se não existe pergunta AGENDA enviada, cria e envia agora.
    """
    q = (
        checkin.questions
        .filter(step="AGENDA")
        .order_by("-scheduled_for", "-id")
        .first()
    )

    # se já tem AGENDA enviada hoje, não reenviar
    if q and q.sent_at:
        return q

    final_msg = agenda_text.format(name=manager.name)

    q = OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA",
        scheduled_for=now,
        sent_at=now,
        status="pending",
        prompt_text=final_msg,  # requer o campo prompt_text
    )

    resp = send_text(manager.phone_e164, final_msg)

    # log do outbound (para o board espelhar)
    _log_outbound(
        manager=manager,
        checkin=checkin,
        related_question=q,
        kind="agenda",
        text=final_msg,
        now=now,
        resp=resp,
    )

    return q


def _should_remind(q: OutboundQuestion, *, now, remind_every_min: int, min_chars: int, max_reminders: int) -> bool:
    """
    Remind se:
      - pending
      - não respondeu
      - reminder_count < max_reminders
      - tempo desde sent_at/last_reminder_at >= remind_every_min
      - e (sem resposta) OU (resposta curta < min_chars)
    """
    if q.status != "pending":
        return False
    if not q.sent_at:
        return False
    if q.answered_at:
        return False
    if q.reminder_count >= max_reminders:
        return False

    base = q.last_reminder_at or q.sent_at
    age_min = (now - base).total_seconds() / 60.0
    if age_min < remind_every_min:
        return False

    txt = (q.answer_text or "").strip()
    if not txt:
        return True
    return len(txt) < min_chars


def _send_reminder(q: OutboundQuestion, *, now, reminder_text: str):
    """
    Envia reminder e registra no log OutboundMessage.
    """
    manager = q.checkin.manager
    if not manager:
        return

    resp = send_text(manager.phone_e164, reminder_text)

    _log_outbound(
        manager=manager,
        checkin=q.checkin,
        related_question=q,
        kind="reminder",
        text=reminder_text,
        now=now,
        resp=resp,
    )

    q.reminder_count += 1
    q.last_reminder_at = now
    q.save(update_fields=["reminder_count", "last_reminder_at"])


def _mark_missed_if_needed(q: OutboundQuestion, *, now, mark_missed_after_min: int):
    if q.status != "pending":
        return
    if not q.sent_at:
        return
    if q.answered_at:
        return

    age_min = (now - q.sent_at).total_seconds() / 60.0
    if age_min >= mark_missed_after_min:
        q.status = "missed"
        q.save(update_fields=["status"])


class Command(BaseCommand):
    help = "Dispara AGENDA e faz reminders/missed. Suporta modo DEV rápido."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true", help="Inclui managers inativos (padrão: False)")
        parser.add_argument("--send-agenda-now", action="store_true", help="Força criar/enviar AGENDA agora (se não enviada ainda)")
        parser.add_argument("--agenda-text", type=str, default=DEFAULT_AGENDA_TEMPLATE, help="Template da mensagem AGENDA (usa {name})")

        # DEV/test knobs
        parser.add_argument("--remind-every-min", type=int, default=15, help="Intervalo mínimo entre reminders (min)")
        parser.add_argument("--max-reminders", type=int, default=4, help="Máximo de reminders")
        parser.add_argument("--min-chars", type=int, default=15, help="Se resposta < min-chars, continua cobrando")
        parser.add_argument("--mark-missed-after-min", type=int, default=120, help="Marca missed após X min pendente")
        parser.add_argument("--reminder-text", type=str, default=DEFAULT_REMINDER_TEXT, help="Texto do reminder (ex: ??)")

    def handle(self, *args, **opts):
        now = timezone.now()

        day = _local_today()
        if opts["date"]:
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        include_inactive = bool(opts["include_inactive"])
        send_agenda_now = bool(opts["send_agenda_now"])
        agenda_text = (opts["agenda_text"] or DEFAULT_AGENDA_TEMPLATE).strip()
        reminder_text = (opts["reminder_text"] or DEFAULT_REMINDER_TEXT).strip() or "??"

        remind_every_min = int(opts["remind_every_min"] or 15)
        max_reminders = int(opts["max_reminders"] or 4)
        min_chars = int(opts["min_chars"] or 15)
        mark_missed_after_min = int(opts["mark_missed_after_min"] or 120)

        managers_qs = (
            Manager.objects.all().order_by("name")
            if include_inactive
            else Manager.objects.filter(is_active=True).order_by("name")
        )

        self.stdout.write(
            f"[checkin_tick] day={day} now={now.isoformat()} managers={managers_qs.count()} include_inactive={include_inactive}"
        )
        self.stdout.write(
            f"[checkin_tick] remind_every_min={remind_every_min} max_reminders={max_reminders} min_chars={min_chars} mark_missed_after_min={mark_missed_after_min}"
        )

        for m in managers_qs:
            checkin = _ensure_checkin(m, day)

            # 1) Envia AGENDA “agora” se pedido
            if send_agenda_now:
                agenda_q = _send_agenda_if_needed(manager=m, checkin=checkin, now=now, agenda_text=agenda_text)
            else:
                agenda_q = (
                    checkin.questions
                    .filter(step="AGENDA")
                    .order_by("-scheduled_for", "-id")
                    .first()
                )

            if not agenda_q:
                continue

            # 2) Marca missed se estourou
            _mark_missed_if_needed(agenda_q, now=now, mark_missed_after_min=mark_missed_after_min)

            # 3) Reminder se necessário (sem resposta ou resposta curta)
            if _should_remind(
                agenda_q,
                now=now,
                remind_every_min=remind_every_min,
                min_chars=min_chars,
                max_reminders=max_reminders,
            ):
                _send_reminder(agenda_q, now=now, reminder_text=reminder_text)
                self.stdout.write(
                    f"  - reminder sent to {m.name} ({m.phone_e164}) count={agenda_q.reminder_count}"
                )

        self.stdout.write(self.style.SUCCESS("[checkin_tick] done"))