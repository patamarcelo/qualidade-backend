# opscheckin/services/flow.py
from django.utils import timezone

from opscheckin.models import DailyCheckin, OutboundQuestion
from opscheckin.services.whatsapp import send_text


FLOW_STEPS = [
    ("AGENDA", "Qual a sua Agenda hoje?"),
    ("STATUS_1", "Check-in 1/5: como está agora? Algum bloqueio?"),
    ("STATUS_2", "Check-in 2/5: como está agora? Algum bloqueio?"),
    ("STATUS_3", "Check-in 3/5: como está agora? Algum bloqueio?"),
    ("STATUS_4", "Check-in 4/5: como está agora? Algum bloqueio?"),
    ("STATUS_5", "Check-in 5/5: fechando o dia — algo pendente/importante?"),
]


def _today_local():
    return timezone.localdate()


def _get_or_create_today_checkin(manager):
    today = _today_local()
    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=today)
    return checkin


def _get_pending_question(checkin):
    return (
        OutboundQuestion.objects.filter(
            checkin=checkin, status="pending", answered_at__isnull=True
        )
        .order_by("scheduled_for")
        .first()
    )


def _next_step_for_checkin(checkin):
    """
    Decide qual o próximo step baseado no que já existe hoje.
    Regra MVP: o próximo é o primeiro step da lista que ainda não foi criado.
    """
    existing_steps = set(
        OutboundQuestion.objects.filter(checkin=checkin).values_list("step", flat=True)
    )
    for step, text in FLOW_STEPS:
        if step not in existing_steps:
            return step, text
    return None, None  # fluxo do dia completo


def create_and_send_next_question(manager, now=None):
    """
    MVP:
      - Se houver pending hoje -> não envia nova
      - Senão -> cria e envia próxima etapa
    """
    if not manager or not getattr(manager, "is_active", False):
        return None

    now = now or timezone.now()
    checkin = _get_or_create_today_checkin(manager)

    pending = _get_pending_question(checkin)
    if pending:
        # já tem pergunta aguardando resposta
        return pending

    step, body = _next_step_for_checkin(checkin)
    if not step:
        return None  # acabou o fluxo hoje

    q = OutboundQuestion.objects.create(
        checkin=checkin,
        step=step,
        scheduled_for=now,
        status="pending",
    )

    # envia
    send_text(manager.phone_e164, body)
    q.sent_at = timezone.now()
    q.save(update_fields=["sent_at"])

    return q
