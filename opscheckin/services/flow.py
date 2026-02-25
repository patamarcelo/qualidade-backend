# opscheckin/services/flow.py
from django.conf import settings
from django.utils import timezone

from opscheckin.models import DailyCheckin, OutboundQuestion
from opscheckin.services.whatsapp import send_text

try:
    # vai existir quando você adicionar o model InboundMessage
    from opscheckin.models import InboundMessage  # type: ignore
except Exception:
    InboundMessage = None  # fallback


FLOW_STEPS = [
    ("AGENDA", "Qual a sua agenda hoje? (pode mandar em tópicos)"),
    ("STATUS_1", "Check-in 1/5: como está agora? Algum bloqueio?"),
    ("STATUS_2", "Check-in 2/5: como está agora? Algum bloqueio?"),
    ("STATUS_3", "Check-in 3/5: como está agora? Algum bloqueio?"),
    ("STATUS_4", "Check-in 4/5: como está agora? Algum bloqueio?"),
    ("STATUS_5", "Fechando o dia — algo pendente/importante?"),
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


def _get_last_question(checkin):
    return (
        OutboundQuestion.objects.filter(checkin=checkin)
        .order_by("-scheduled_for", "-id")
        .first()
    )


def _next_step_for_checkin(checkin):
    """
    Decide próximo step baseado no que já existe hoje.
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
        return pending

    step, body = _next_step_for_checkin(checkin)
    if not step:
        return None

    q = OutboundQuestion.objects.create(
        checkin=checkin,
        step=step,
        scheduled_for=now,
        status="pending",
    )

    resp = send_text(manager.phone_e164, body)

    q.sent_at = timezone.now()
    # opcional: se depois você adicionar campo no model p/ guardar wamid, já fica pronto:
    if hasattr(q, "provider_message_id"):
        try:
            q.provider_message_id = (resp.get("messages") or [{}])[0].get("id") or ""
        except Exception:
            pass

    q.save(update_fields=[f for f in ["sent_at", "provider_message_id"] if hasattr(q, f)])
    return q


def ingest_inbound_and_maybe_advance(manager, text: str, received_at=None):
    """
    Novo fluxo:
      - SEMPRE grava inbound (Inbox)
      - Se houver OutboundQuestion pending hoje: tenta linkar e marcar answered
      - Se NÃO houver pending: ainda grava inbound como "spontaneous" / sem link
      - Opcional: pode avançar e mandar a próxima pergunta automaticamente
    """
    if not manager or not getattr(manager, "is_active", False):
        return {"ok": True, "detail": "manager_inactive"}

    received_at = received_at or timezone.now()
    checkin = _get_or_create_today_checkin(manager)

    # 1) grava inbound SEMPRE (quando model existir)
    inbound_obj = None
    pending = _get_pending_question(checkin)
    last_q = _get_last_question(checkin)

    if InboundMessage is not None:
        inbound_obj = InboundMessage.objects.create(
            manager=manager,
            checkin=checkin,
            text=(text or "").strip(),
            received_at=received_at,
            # linka no pending se existir, senão tenta linkar na última pergunta do dia (opcional)
            question=pending if pending else None,
            # status simples para ajudar debug / inbox
            kind="answer" if pending else "spontaneous",
        )

    # 2) se há pending: marca answered
    if pending:
        pending.answered_at = received_at

        # comportamento importante:
        # se ele mandar 3 mensagens separadas, você decide:
        # (A) sobrescrever (atual)
        # (B) concatenar (recomendado)
        mode = getattr(settings, "OPS_INBOUND_APPEND_MODE", "append")  # append|overwrite

        if mode == "overwrite":
            pending.answer_text = (text or "").strip()
        else:
            # append: preserva o que já tinha
            prev = (pending.answer_text or "").strip()
            cur = (text or "").strip()
            pending.answer_text = cur if not prev else (prev + "\n" + cur)

        pending.status = "answered"
        pending.save(update_fields=["answered_at", "answer_text", "status"])

        # 3) avanço opcional automático
        auto_advance = getattr(settings, "OPS_AUTO_ADVANCE_ON_REPLY", False)
        if auto_advance:
            next_q = create_and_send_next_question(manager, now=timezone.now())
            return {
                "ok": True,
                "linked": True,
                "pending_was": pending.step,
                "advanced": bool(next_q and next_q.id != pending.id),
                "next_step": getattr(next_q, "step", None),
            }

        return {"ok": True, "linked": True, "pending_step": pending.step}

    # 4) sem pending: inbound foi “spontaneous”
    # aqui você pode chamar um “processor/agent” no futuro.
    # por enquanto só retorna info.
    return {
        "ok": True,
        "linked": False,
        "detail": "no_pending_question",
        "last_step": getattr(last_q, "step", None),
        "inbound_id": getattr(inbound_obj, "id", None),
    }