from django.utils import timezone
from opscheckin.models import OutboundQuestion
from opscheckin.services.whatsapp import send_text


REMINDER_AFTER_MIN = 30
MARK_MISSED_AFTER_MIN = 120


def process_pending(now=None):
    """
    - 1ª cobrança após REMINDER_AFTER_MIN (apenas 1 vez)
    - marca missed após MARK_MISSED_AFTER_MIN
    """
    now = now or timezone.now()

    pending = (
        OutboundQuestion.objects
        .filter(status="pending", sent_at__isnull=False, answered_at__isnull=True)
        .select_related("checkin__manager")
        .order_by("scheduled_for", "id")
    )

    for q in pending:
        age_min = (now - q.sent_at).total_seconds() / 60.0

        if age_min >= MARK_MISSED_AFTER_MIN:
            q.status = "missed"
            q.save(update_fields=["status"])
            continue

        if age_min >= REMINDER_AFTER_MIN and q.reminder_count == 0:
            reminder = (
                "Só confirmando 🙂\n"
                "Ainda não recebi sua resposta da última pergunta.\n"
                "Quando puder, responde aqui mesmo."
            )
            send_text(q.checkin.manager.phone_e164, reminder)
            q.reminder_count = 1
            q.last_reminder_at = now
            q.save(update_fields=["reminder_count", "last_reminder_at"])