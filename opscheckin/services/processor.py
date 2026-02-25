# opscheckin/services/processor.py
import logging
from django.utils import timezone

from opscheckin.models import InboundMessage

logger = logging.getLogger("opscheckin.processor")


def process_inbound_messages(limit: int = 100):
    """
    Esqueleto: processa mensagens inbound NÃO processadas.
    No futuro: classifica intenção, atualiza estado, dispara próxima pergunta, etc.
    """
    qs = (
        InboundMessage.objects
        .filter(processed=False)
        .order_by("received_at")[:limit]
    )

    count = 0
    for m in qs:
        # Aqui entra o "cérebro" (regras, LLM, consultas ao banco, etc.)
        logger.info("PROCESS inbound id=%s from=%s text=%s", m.id, m.from_phone, (m.text or "")[:80])

        m.processed = True
        m.processed_at = timezone.now()
        m.save(update_fields=["processed", "processed_at"])
        count += 1

    return count