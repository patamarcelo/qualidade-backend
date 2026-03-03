from django.utils import timezone
from django.db import transaction
from opscheckin.models import OutboundQuestion

# Regras
MIN_VALID_CHARS = 15
WINDOW_MIN = 60  # após 60 min do sent_at: missed

# Slots cravados (minutos após o envio às 06:00)
# Se você quiser “de fato” prender em horários do dia, use localtime + replace.
REMINDER_SLOTS = [
    (6, 15, 0),
    (6, 30, 1),
    (6, 45, 2),
    (7, 0, 3),
]

SLOT_GRACE_SECONDS = 120  # 2 min
REMINDER_TEXT = "??"


def _is_answer_valid(q: OutboundQuestion) -> bool:
    txt = (q.answer_text or "").strip()
    return len(txt) >= MIN_VALID_CHARS


def _slot_window(local_now, hour: int, minute: int, grace_seconds: int):
    start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timezone.timedelta(seconds=grace_seconds)
    return start, end


def _is_in_slot(local_now, hour: int, minute: int, grace_seconds: int) -> bool:
    start, end = _slot_window(local_now, hour, minute, grace_seconds)
    return start <= local_now < end


def _already_sent_in_this_slot(q: OutboundQuestion, *, local_now, hour: int, minute: int, grace_seconds: int) -> bool:
    anchor = q.last_reminder_at or q.sent_at
    if not anchor:
        return False
    anchor_local = timezone.localtime(anchor)
    start, end = _slot_window(local_now, hour, minute, grace_seconds)
    return start <= anchor_local < end


def process_agenda_reminders(now=None):
    """
    - Só AGENDA pending e enviada
    - Se resposta inválida, cobra nos slots (06:15/06:30/06:45/07:00)
    - Máximo 4 reminders
    - Após 60 min desde sent_at: missed
    - Usa fallback: texto se dentro 24h, senão template (se configurado)
    """
    # Import aqui pra não criar dependência circular caso você organize diferente
    from opscheckin.management.commands.checkin_tick import _send_with_fallback

    now = now or timezone.now()
    local_now = timezone.localtime(now)

    # Descobre se AGORA é um slot e qual o reminder_count esperado nesse slot
    current_slot = None
    for (hh, mm, expected_count) in REMINDER_SLOTS:
        if _is_in_slot(local_now, hh, mm, SLOT_GRACE_SECONDS):
            current_slot = (hh, mm, expected_count)
            break

    # Se não é slot, não faz nada (evita spam)
    if not current_slot:
        return

    hh, mm, expected_count = current_slot

    qs = (
        OutboundQuestion.objects
        .filter(
            step="AGENDA",
            status="pending",
            sent_at__isnull=False,
            answered_at__isnull=True,
        )
        .select_related("checkin__manager")
        .order_by("sent_at")
    )

    for q in qs:
        # Revalida resposta (fallback)
        if _is_answer_valid(q):
            q.answered_at = now
            q.status = "answered"
            q.save(update_fields=["answered_at", "status"])
            continue

        # Janela de 60 min desde envio
        age_min = (now - q.sent_at).total_seconds() / 60.0
        if age_min >= WINDOW_MIN:
            q.status = "missed"
            q.save(update_fields=["status"])
            continue

        # Só dispara se estiver exatamente no “expected_count” do slot
        # Ex: 06:15 espera reminder_count==0; 06:30 espera ==1; etc
        if q.reminder_count != expected_count:
            continue

        # Já mandou algo nesse slot? não manda de novo
        if _already_sent_in_this_slot(q, local_now=local_now, hour=hh, minute=mm, grace_seconds=SLOT_GRACE_SECONDS):
            continue

        manager = q.checkin.manager
        if not manager:
            continue

        # Envia (texto se dentro 24h; template se fora 24h)
        resp = _send_with_fallback(
            manager=manager,
            kind="reminder",
            text_body=REMINDER_TEXT,
            template_name="",  # usa settings WHATSAPP_TEMPLATE_REMINDER_NAME
            template_params={
                # ajuste para bater com o seu template de reminder (se for nomeado)
                "manager_name": manager.name,
            },
        )

        if not resp:
            # não incrementa reminder_count se falhou (pra tentar no próximo slot)
            continue

        # Atualiza counters de forma segura
        with transaction.atomic():
            # recarrega com lock leve pra evitar double-send se tiver concorrência
            q_locked = (
                OutboundQuestion.objects
                .select_for_update()
                .get(pk=q.pk)
            )
            # se alguém já incrementou, não duplica
            if q_locked.reminder_count != expected_count:
                continue

            q_locked.reminder_count += 1
            q_locked.last_reminder_at = now
            q_locked.save(update_fields=["reminder_count", "last_reminder_at"])