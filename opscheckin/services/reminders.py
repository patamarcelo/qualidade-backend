from django.utils import timezone
from .whatsapp import send_text
from ..models import OutboundQuestion


def process_reminders():
    now = timezone.now()

    pending = OutboundQuestion.objects.filter(
        status="pending",
        sent_at__isnull=False,
        answered_at__isnull=True,
        reminder_count__lt=2,
        sent_at__lte=now - timezone.timedelta(minutes=30),
    )

    for q in pending:
        send_text(
            q.checkin.manager.phone_e164,
            "Ainda não recebi sua resposta 👀",
        )

        q.reminder_count += 1
        q.last_reminder_at = now
        q.save(update_fields=["reminder_count", "last_reminder_at"])