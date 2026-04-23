from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from opscheckin.models import (
    InboundMessage,
    Manager,
    ManagerNotificationSubscription,
    NotificationType,
    OutboundMessage,
)

# AJUSTE ESTES IMPORTS para os models novos que você criou.
# Estou assumindo estes nomes:
from opscheckin.models import (
    ManagerPersonalReminder,
    ManagerPersonalReminderDispatch,
)


from opscheckin.services.whatsapp import send_text, send_template

logger = logging.getLogger(__name__)


PERSONAL_REMINDER_NOTIFICATION_CODE = "personal_reminder"
OUTBOUND_KIND_PERSONAL_REMINDER = "personal_reminder"


@dataclass
class ReminderSendResult:
    ok: bool
    status: str
    dispatch_id: Optional[int] = None
    provider_message_id: str = ""
    detail: str = ""


def _local_now() -> datetime:
    return timezone.localtime(timezone.now())


def _combine_local(day, t: time) -> datetime:
    naive = datetime.combine(day, t)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def get_managers_subscribed_to_personal_reminders():
    """
    Managers com subscription ativa do tipo personal_reminder.
    Mantém coerência com o padrão atual de NotificationType + Subscription.
    """
    return (
        Manager.objects.filter(
            notification_subscriptions__notification_type__code=PERSONAL_REMINDER_NOTIFICATION_CODE,
            notification_subscriptions__notification_type__is_active=True,
            notification_subscriptions__is_active=True,
        )
        .distinct()
        .order_by("name")
    )


def reminder_matches_day(reminder: ManagerPersonalReminder, day) -> bool:
    if reminder.start_date and day < reminder.start_date:
        return False

    if reminder.end_date and day > reminder.end_date:
        return False

    schedule_type = getattr(reminder, "schedule_type", "")

    if schedule_type == "daily":
        return True

    if schedule_type == "weekly":
        return reminder.weekday == day.weekday()

    if schedule_type == "monthly":
        return reminder.day_of_month == day.day

    return False


def reminder_matches_now(
    reminder: ManagerPersonalReminder,
    now_local: Optional[datetime] = None,
) -> bool:
    """
    Considera elegível quando:
    - a regra vale para o dia
    - agora está entre o horário alvo e o fim da janela
    """
    now_local = now_local or _local_now()
    day = now_local.date()

    if not reminder_matches_day(reminder, day):
        return False

    target_dt = _combine_local(day, reminder.time_of_day)
    allowed_window_minutes = int(getattr(reminder, "allowed_window_minutes", 30) or 30)
    window_end = target_dt + timedelta(minutes=allowed_window_minutes)

    return target_dt <= now_local <= window_end


def get_pending_dispatch_for_inbound(
    manager: Manager,
    *,
    now_local: Optional[datetime] = None,
    lookback_hours: int = 24,
) -> Optional[ManagerPersonalReminderDispatch]:
    """
    Busca o dispatch pendente mais recente do manager.
    Restringe a janela para reduzir matches indevidos.
    """
    now_local = now_local or _local_now()
    min_dt = now_local - timedelta(hours=lookback_hours)

    return (
        ManagerPersonalReminderDispatch.objects.select_related("reminder", "manager")
        .filter(
            manager=manager,
            status="pending",
            scheduled_for__gte=min_dt,
            scheduled_for__lte=now_local,
        )
        .order_by("-scheduled_for", "-id")
        .first()
    )


def build_personal_reminder_text(reminder: ManagerPersonalReminder) -> str:
    """
    Texto final da mensagem.
    Mantive simples no início.
    """
    return (reminder.message_text or "").strip()


def _send_text_message(*, to_phone: str, text: str):
    resp = send_text(to_phone, text)

    provider_message_id = ""
    try:
        provider_message_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        provider_message_id = ""

    return {
        "ok": True,
        "provider_message_id": provider_message_id,
        "raw_response": resp,
        "wa_status": "sent" if provider_message_id else "",
    }


def _send_template_message(
    *,
    to_phone: str,
    template_name: str,
    language: str = "pt_BR",
    reminder: ManagerPersonalReminder | None = None,
):
    manager_name = ""
    message_text = ""

    if reminder is not None:
        manager_name = getattr(reminder.manager, "name", "") or ""
        message_text = (getattr(reminder, "message_text", "") or "").strip()

    body_params = [manager_name, message_text]

    quick_reply_payloads = None
    if reminder is not None and getattr(reminder, "response_mode", "") == "button":
        quick_reply_payloads = ["PR:CONFIRM"]

    resp = send_template(
        to_phone,
        template_name=template_name,
        language_code=language,
        body_params=body_params,
        quick_reply_payloads=quick_reply_payloads,
    )

    provider_message_id = ""
    try:
        provider_message_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        provider_message_id = ""

    return {
        "ok": True,
        "provider_message_id": provider_message_id,
        "raw_response": resp,
        "wa_status": "sent" if provider_message_id else "",
    }
    
    
def send_manager_personal_reminder(
    reminder: ManagerPersonalReminder,
    *,
    now_local: Optional[datetime] = None,
    force: bool = False,
) -> ReminderSendResult:
    now_local = now_local or _local_now()
    reference_date = now_local.date()

    if not reminder.is_active:
        return ReminderSendResult(ok=False, status="inactive", detail="Reminder inativo.")

    if not force and not reminder_matches_now(reminder, now_local=now_local):
        return ReminderSendResult(ok=False, status="out-of-window", detail="Fora da janela de envio.")

    if not getattr(reminder, "manager_id", None):
        return ReminderSendResult(ok=False, status="no-manager", detail="Reminder sem manager.")

    manager = reminder.manager

    # Segurança extra: exige subscription ativa do tipo personal_reminder
    is_subscribed = ManagerNotificationSubscription.objects.filter(
        manager=manager,
        notification_type__code=PERSONAL_REMINDER_NOTIFICATION_CODE,
        notification_type__is_active=True,
        is_active=True,
    ).exists()

    if not is_subscribed:
        return ReminderSendResult(
            ok=False,
            status="not-subscribed",
            detail="Manager sem subscription ativa para personal_reminder.",
        )

    scheduled_for = _combine_local(reference_date, reminder.time_of_day)

    existing = (
        ManagerPersonalReminderDispatch.objects.filter(
            reminder=reminder,
            manager=manager,
            reference_date=reference_date,
        )
        .order_by("-id")
        .first()
    )
    if existing:
        return ReminderSendResult(
            ok=True,
            status="already-dispatched",
            dispatch_id=existing.id,
            provider_message_id=existing.provider_message_id or "",
            detail="Dispatch já existente para a data de referência.",
        )

    text_to_send = build_personal_reminder_text(reminder)

    delivery_mode = getattr(reminder, "delivery_mode", "text")
    response_mode = getattr(reminder, "response_mode", "none")

    provider_message_id = ""
    raw_response = None
    wa_status = ""
    outbound_message = None

    try:
        with transaction.atomic():
            dispatch_status = "pending" if response_mode in ("text", "button") else "sent"

            dispatch = ManagerPersonalReminderDispatch.objects.create(
                reminder=reminder,
                manager=manager,
                reference_date=reference_date,
                scheduled_for=scheduled_for,
                status=dispatch_status,
            )

            if delivery_mode == "template":
                template_name = (
                    reminder.get_effective_template_name()
                    if hasattr(reminder, "get_effective_template_name")
                    else (reminder.template_name or "")
                )

                send_result = _send_template_message(
                    to_phone=manager.phone_e164,
                    template_name=template_name,
                    language=getattr(reminder, "template_language", "pt_BR") or "pt_BR",
                    reminder=reminder,
                )
                
            else:
                send_result = _send_text_message(
                    to_phone=manager.phone_e164,
                    text=text_to_send,
                )

            provider_message_id = (send_result or {}).get("provider_message_id", "") or ""
            raw_response = (send_result or {}).get("raw_response")
            wa_status = (send_result or {}).get("wa_status", "") or "sent"

            outbound_message = OutboundMessage.objects.create(
                manager=manager,
                to_phone=manager.phone_e164,
                provider_message_id=provider_message_id,
                kind=OUTBOUND_KIND_PERSONAL_REMINDER,
                text=text_to_send,
                sent_at=now_local,
                raw_response=raw_response,
                wa_status=wa_status if wa_status in {"sent", "delivered", "read", "failed"} else "",
                wa_sent_at=now_local if wa_status in {"sent", "delivered", "read"} else None,
            )

            dispatch.sent_at = now_local
            dispatch.provider_message_id = provider_message_id
            dispatch.outbound_message = outbound_message
            dispatch.raw_response_payload = raw_response
            dispatch.save(
                update_fields=[
                    "sent_at",
                    "provider_message_id",
                    "outbound_message",
                    "raw_response_payload",
                ]
            )

            logger.info(
                "[personal_reminder_send] ok manager=%s reminder=%s dispatch=%s mode=%s response_mode=%s",
                manager.name,
                reminder.title,
                dispatch.id,
                delivery_mode,
                response_mode,
            )

            return ReminderSendResult(
                ok=True,
                status="sent",
                dispatch_id=dispatch.id,
                provider_message_id=provider_message_id,
            )

    except IntegrityError:
        # concorrência / cron duplicado / execução simultânea
        existing = (
            ManagerPersonalReminderDispatch.objects.filter(
                reminder=reminder,
                manager=manager,
                reference_date=reference_date,
            )
            .order_by("-id")
            .first()
        )
        return ReminderSendResult(
            ok=True,
            status="already-dispatched",
            dispatch_id=existing.id if existing else None,
            provider_message_id=existing.provider_message_id if existing else "",
            detail="Dispatch já criado em outra transação.",
        )
    except Exception as exc:
        logger.exception(
            "[personal_reminder_send] failed manager=%s reminder=%s error=%s",
            manager.name,
            reminder.title,
            exc,
        )

        # tenta registrar falha mínima
        try:
            dispatch = ManagerPersonalReminderDispatch.objects.create(
                reminder=reminder,
                manager=manager,
                reference_date=reference_date,
                scheduled_for=scheduled_for,
                status="failed",
                notes=str(exc)[:255],
            )
            return ReminderSendResult(
                ok=False,
                status="failed",
                dispatch_id=dispatch.id,
                detail=str(exc),
            )
        except Exception:
            return ReminderSendResult(
                ok=False,
                status="failed",
                detail=str(exc),
            )


def try_link_personal_reminder_response(inbound: InboundMessage) -> bool:
    """
    Deve ser chamada depois que o InboundMessage já foi salvo.

    Regras:
    - response_mode=button: fecha com msg_type button/interactive
    - response_mode=text: fecha com texto
    - salva answered_at, answer_text e answer_source
    """
    if not inbound or not inbound.manager_id:
        return False

    manager = inbound.manager
    now_local = timezone.localtime(inbound.received_at) if inbound.received_at else _local_now()

    dispatch = get_pending_dispatch_for_inbound(manager, now_local=now_local)
    if not dispatch:
        return False

    reminder = dispatch.reminder
    response_mode = getattr(reminder, "response_mode", "none")
    msg_type = (inbound.msg_type or "").strip().lower()
    inbound_text = (inbound.text or "").strip()

    answer_source = None

    if response_mode == "button":
        if msg_type not in {"button", "interactive"}:
            return False
        answer_source = "button"

    elif response_mode == "text":
        if not inbound_text:
            return False
        answer_source = "text"

    else:
        return False

    dispatch.status = "answered"
    dispatch.answered_at = inbound.received_at or timezone.now()
    dispatch.answer_text = inbound_text
    dispatch.answer_source = answer_source
    dispatch.inbound_message = inbound
    dispatch.save(
        update_fields=[
            "status",
            "answered_at",
            "answer_text",
            "answer_source",
            "inbound_message",
        ]
    )

    logger.info(
        "[personal_reminder_response] manager=%s dispatch=%s source=%s answered_at=%s",
        manager.name,
        dispatch.id,
        answer_source,
        dispatch.answered_at,
    )
    return True


def expire_old_pending_personal_reminders(*, now_local: Optional[datetime] = None, max_age_hours: int = 24) -> int:
    """
    Opcional, mas útil para limpeza operacional.
    """
    now_local = now_local or _local_now()
    threshold = now_local - timedelta(hours=max_age_hours)

    qs = ManagerPersonalReminderDispatch.objects.filter(
        status="pending",
        scheduled_for__lt=threshold,
    )

    updated = qs.update(status="missed")
    if updated:
        logger.info("[personal_reminder_expire] updated=%s threshold=%s", updated, threshold)
    return updated


def run_personal_reminder_tick(*, now_local: Optional[datetime] = None):
    now_local = now_local or _local_now()

    reminders = (
        ManagerPersonalReminder.objects.select_related("manager")
        .filter(
            is_active=True,
            manager__notification_subscriptions__notification_type__code=PERSONAL_REMINDER_NOTIFICATION_CODE,
            manager__notification_subscriptions__notification_type__is_active=True,
            manager__notification_subscriptions__is_active=True,
        )
        .distinct()
        .order_by("manager__name", "time_of_day", "id")
    )

    analyzed = 0
    eligible = 0
    sent = 0
    existing = 0
    failed = 0

    for reminder in reminders:
        analyzed += 1

        if not reminder_matches_now(reminder, now_local=now_local):
            continue

        eligible += 1
        result = send_manager_personal_reminder(reminder, now_local=now_local)

        if result.status == "sent":
            sent += 1
        elif result.status == "already-dispatched":
            existing += 1
        elif not result.ok:
            failed += 1

    expired = expire_old_pending_personal_reminders(now_local=now_local, max_age_hours=24)

    logger.info(
        "[manager_personal_reminder_tick] reminders=%s eligible=%s sent=%s existing=%s failed=%s expired=%s",
        analyzed,
        eligible,
        sent,
        existing,
        failed,
        expired,
    )

    return {
        "reminders": analyzed,
        "eligible": eligible,
        "sent": sent,
        "existing": existing,
        "failed": failed,
        "expired": expired,
    }