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

# JANELA OFICIAL
AGENDA_HOUR = 6
AGENDA_MINUTE = 0

# Reminders “cravados” (modelo A)
# (hour, minute, expected_reminder_count)
REMINDER_SLOTS = [
    (6, 15, 0),
    (6, 30, 1),
    (6, 45, 2),
    (7, 0, 3),
]

MIN_CHARS_DEFAULT = 15
MARK_MISSED_AFTER_MIN_DEFAULT = 120

# tolerância pra “pegar” o slot caso o job rode alguns segundos/minutos atrasado
SLOT_GRACE_SECONDS_DEFAULT = 120  # 2 min


def _local_today():
    return timezone.localdate()


def _ensure_checkin(manager: Manager, day):
    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=day)
    return checkin


def _log_outbound(
    *,
    manager: Manager,
    checkin: DailyCheckin,
    related_question: OutboundQuestion | None,
    kind: str,
    text: str,
    now,
    resp: dict | None,
):
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


def _send_agenda_if_needed(*, manager: Manager, checkin: DailyCheckin, now, agenda_text: str):
    """
    Garante que existe UMA pergunta AGENDA enviada no dia.
    Só cria/envia se ainda não tiver AGENDA com sent_at.
    """
    q = (
        checkin.questions
        .filter(step="AGENDA")
        .order_by("-scheduled_for", "-id")
        .first()
    )

    if q and q.sent_at:
        return q

    final_msg = agenda_text.format(name=manager.name)

    q = OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA",
        scheduled_for=now,
        sent_at=now,
        status="pending",
        prompt_text=final_msg,  # requer campo prompt_text
    )

    resp = send_text(manager.phone_e164, final_msg)

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


def _needs_followup(q: OutboundQuestion, *, min_chars: int) -> bool:
    """
    Se não respondeu ou respondeu curto demais, continua cobrando.
    """
    if q.status != "pending":
        return False
    if not q.sent_at:
        return False
    if q.answered_at:
        return False

    txt = (q.answer_text or "").strip()
    if not txt:
        return True
    return len(txt) < min_chars


def _slot_window(local_now, hour: int, minute: int, grace_seconds: int):
    """
    Retorna (slot_start, slot_end) em timezone local.
    """
    start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timezone.timedelta(seconds=grace_seconds)
    return start, end


def _is_in_slot(local_now, hour: int, minute: int, grace_seconds: int) -> bool:
    start, end = _slot_window(local_now, hour, minute, grace_seconds)
    return start <= local_now < end


def _already_sent_in_this_slot(q: OutboundQuestion, *, local_now, hour: int, minute: int, grace_seconds: int) -> bool:
    """
    Evita duplicar reminder se o job rodar mais de uma vez dentro do grace window.
    Usamos last_reminder_at (ou sent_at) para ver se já “caiu” nesse slot.
    """
    anchor = q.last_reminder_at or q.sent_at
    if not anchor:
        return False

    anchor_local = timezone.localtime(anchor)
    start, end = _slot_window(local_now, hour, minute, grace_seconds)
    return start <= anchor_local < end


def _send_reminder(q: OutboundQuestion, *, now, reminder_text: str):
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


class Command(BaseCommand):
    help = "Dispara AGENDA e faz reminders/missed (modelo A: horários cravados)."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true", help="Inclui managers inativos (padrão: False)")
        parser.add_argument("--send-agenda-now", action="store_true", help="Força criar/enviar AGENDA agora (se não enviada ainda)")
        parser.add_argument("--agenda-text", type=str, default=DEFAULT_AGENDA_TEMPLATE, help="Template da AGENDA (usa {name})")

        parser.add_argument("--min-chars", type=int, default=MIN_CHARS_DEFAULT, help="Se resposta < min-chars, continua cobrando")
        parser.add_argument("--max-reminders", type=int, default=4, help="Máximo reminders (default: 4)")
        parser.add_argument("--mark-missed-after-min", type=int, default=MARK_MISSED_AFTER_MIN_DEFAULT, help="Marca missed após X min pendente")
        parser.add_argument("--reminder-text", type=str, default=DEFAULT_REMINDER_TEXT, help="Texto do reminder (ex: ??)")
        parser.add_argument("--slot-grace-seconds", type=int, default=SLOT_GRACE_SECONDS_DEFAULT, help="Janela de tolerância do slot")

    def handle(self, *args, **opts):
        now = timezone.now()
        local_now = timezone.localtime(now)

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

        min_chars = int(opts["min_chars"] or MIN_CHARS_DEFAULT)
        max_reminders = int(opts["max_reminders"] or 4)
        mark_missed_after_min = int(opts["mark_missed_after_min"] or MARK_MISSED_AFTER_MIN_DEFAULT)
        grace_seconds = int(opts["slot_grace_seconds"] or SLOT_GRACE_SECONDS_DEFAULT)

        managers_qs = (
            Manager.objects.all().order_by("name")
            if include_inactive
            else Manager.objects.filter(is_active=True).order_by("name")
        )

        self.stdout.write(
            f"[checkin_tick] day={day} now={now.isoformat()} local_now={local_now.isoformat()} managers={managers_qs.count()} include_inactive={include_inactive}"
        )

        # Descobre se AGORA é um slot de reminder e qual expected_count
        current_slot = None
        for (hh, mm, expected_count) in REMINDER_SLOTS:
            if _is_in_slot(local_now, hh, mm, grace_seconds):
                current_slot = (hh, mm, expected_count)
                break

        for m in managers_qs:
            checkin = _ensure_checkin(m, day)

            # 1) AGENDA às 06:00 (ou forçado)
            agenda_q = (
                checkin.questions
                .filter(step="AGENDA")
                .order_by("-scheduled_for", "-id")
                .first()
            )

            if send_agenda_now:
                agenda_q = _send_agenda_if_needed(manager=m, checkin=checkin, now=now, agenda_text=agenda_text)
            else:
                # se estamos exatamente em 06:00 (com grace) e ainda não enviou, envia
                if _is_in_slot(local_now, AGENDA_HOUR, AGENDA_MINUTE, grace_seconds):
                    agenda_q = _send_agenda_if_needed(manager=m, checkin=checkin, now=now, agenda_text=agenda_text)

            if not agenda_q:
                continue

            # 2) missed
            _mark_missed_if_needed(agenda_q, now=now, mark_missed_after_min=mark_missed_after_min)

            # 3) reminders cravados por reminder_count
            if not current_slot:
                continue  # não é horário de reminder

            hh, mm, expected_count = current_slot

            # só até max_reminders-1 (0..3)
            if agenda_q.reminder_count >= max_reminders:
                continue

            # só dispara no slot “correto” pro reminder_count atual
            if agenda_q.reminder_count != expected_count:
                continue

            # não duplica dentro do mesmo slot
            if _already_sent_in_this_slot(agenda_q, local_now=local_now, hour=hh, minute=mm, grace_seconds=grace_seconds):
                continue

            # só cobra se ainda precisa (sem resposta ou curta)
            if not _needs_followup(agenda_q, min_chars=min_chars):
                continue

            _send_reminder(agenda_q, now=now, reminder_text=reminder_text)
            self.stdout.write(f"  - reminder sent slot={hh:02d}:{mm:02d} to {m.name} count={agenda_q.reminder_count}")

        self.stdout.write(self.style.SUCCESS("[checkin_tick] done"))