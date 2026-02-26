from django.utils import timezone
from opscheckin.models import DailyCheckin, OutboundQuestion, InboundMessage


def link_inbound_to_pending(checkin: DailyCheckin, inbound: InboundMessage, now=None):
    """
    Linka uma mensagem inbound à pergunta pending mais apropriada.
    Regra: pending mais recentemente enviada (sent_at desc).
    """
    now = now or timezone.now()

    pending = (
        OutboundQuestion.objects.filter(
            checkin=checkin,
            status="pending",
            answered_at__isnull=True,
        )
        .order_by("-sent_at", "scheduled_for", "id")
        .first()
    )

    if not pending:
        return None

    pending.answered_at = now
    prev = (pending.answer_text or "").strip()
    cur = (inbound.text or "").strip()
    pending.answer_text = cur if not prev else (prev + "\n" + cur)
    pending.status = "answered"
    pending.save(update_fields=["answered_at", "answer_text", "status"])

    inbound.linked_question = pending
    inbound.processed = True
    inbound.processed_at = now
    inbound.save(update_fields=["linked_question", "processed", "processed_at"])

    return pending