from django.utils import timezone
from .whatsapp import send_text_message
from ..models import DailyCheckin, OutboundQuestion


def send_agenda_question(manager):
    today = timezone.localdate()

    checkin, _ = DailyCheckin.objects.get_or_create(
        manager=manager,
        date=today,
    )

    question = OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA",
        scheduled_for=timezone.now(),
    )

    message = (
        f"Bom dia, {manager.name}.\n\n"
        "Qual é a agenda principal de hoje?"
    )

    result = send_text_message(manager.phone_e164, message)

    question.sent_at = timezone.now()
    question.save(update_fields=["sent_at"])

    return result