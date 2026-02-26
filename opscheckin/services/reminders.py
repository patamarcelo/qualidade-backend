from django.utils import timezone
from opscheckin.models import OutboundQuestion
from opscheckin.services.whatsapp import send_text

# escopo
REMINDER_EVERY_MIN = 15
MAX_REMINDERS = 4          # 06:15, 06:30, 06:45, 07:00 (considerando sent_at 06:00)
WINDOW_MIN = 60            # consolida até 07:00
MIN_VALID_CHARS = 15

REMINDER_TEXT = "??"


def _is_answer_valid(q: OutboundQuestion) -> bool:
    txt = (q.answer_text or "").strip()
    return len(txt) >= MIN_VALID_CHARS


def process_agenda_reminders(now=None):
    """
    Regras:
    - Só aplica em step='AGENDA'
    - Se ainda não tem resposta válida (<15 chars), cobra a cada 15 min
    - Máximo 4 cobranças
    - Após 60 min (07:00 se sent_at=06:00): marca missed se ainda inválido
    """
    now = now or timezone.now()

    qs = (
        OutboundQuestion.objects
        .filter(
            step="AGENDA",
            status="pending",
            sent_at__isnull=False,
            answered_at__isnull=True,  # ainda não consideramos "respondido"
        )
        .select_related("checkin__manager")
    )

    for q in qs:
        # janela de 60 min desde o envio
        age_min = (now - q.sent_at).total_seconds() / 60.0

        # se por algum motivo answer_text ficou bom mas answered_at não foi setado
        if _is_answer_valid(q):
            q.answered_at = now
            q.status = "answered"
            q.save(update_fields=["answered_at", "status"])
            continue

        # encerra janela
        if age_min >= WINDOW_MIN:
            q.status = "missed"
            q.save(update_fields=["status"])
            continue

        # calcula quantas cobranças "deveriam" ter ocorrido até agora
        should_have = int(age_min // REMINDER_EVERY_MIN)  # 0..4
        # só dispara se já passou de pelo menos 15 min
        if should_have <= 0:
            continue

        # limita ao máximo
        should_have = min(should_have, MAX_REMINDERS)

        # se ainda não enviamos a quantidade esperada, envia 1 agora
        if q.reminder_count < should_have:
            send_text(q.checkin.manager.phone_e164, REMINDER_TEXT)
            q.reminder_count += 1
            q.last_reminder_at = now
            q.save(update_fields=["reminder_count", "last_reminder_at"])