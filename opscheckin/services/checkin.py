from datetime import datetime
from django.utils import timezone

from opscheckin.models import DailyCheckin, OutboundQuestion
from opscheckin.services.flow import SLOTS, slot_text
from opscheckin.services.whatsapp import send_text


def _local_today():
    return timezone.localdate()


def _slot_dt(today, slot_time):
    # cria datetime local para o slot
    return timezone.make_aware(datetime.combine(today, slot_time))


def ensure_slots_for_today(manager, today=None):
    today = today or _local_today()
    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=today)

    for step, t, _text in SLOTS:
        scheduled_for = _slot_dt(today, t)
        OutboundQuestion.objects.get_or_create(
            checkin=checkin,
            step=step,
            defaults={"scheduled_for": scheduled_for, "status": "pending"},
        )

    return checkin


def send_due_questions(checkin, now=None):
    """
    Envia perguntas cujo scheduled_for <= now e sent_at ainda é null.
    Retorna lista de OutboundQuestion enviadas.
    """
    now = now or timezone.now()

    due = (
        checkin.questions
        .filter(sent_at__isnull=True, scheduled_for__lte=now)
        .order_by("scheduled_for", "id")
    )

    sent = []
    for q in due:
        body = slot_text(q.step) or f"[{q.step}]"
        send_text(checkin.manager.phone_e164, body)
        q.sent_at = now
        q.status = "pending"
        q.save(update_fields=["sent_at", "status"])
        sent.append(q)

    return sent