from __future__ import annotations

import logging
from datetime import date, timedelta
import calendar

from typing import Iterable

from django.db.models import Q
from django.utils import timezone

from opscheckin.models import (
    Manager,
    ManagerPersonalReminder,
    ManagerPersonalReminderDispatch,
    OutboundMessage,
)

from opscheckin.services.whatsapp import send_template, send_text

logger = logging.getLogger(__name__)


TEMPLATE_COORDINATOR_CONFIRMED = "coordinator_personal_reminder_confirmed"
TEMPLATE_COORDINATOR_DAILY_ACTION = "coordinator_personal_reminders_daily_action"

PAYLOAD_COORDINATOR_DAILY = "CR:DAILY"


def _extract_provider_message_id(resp) -> str:
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""


def _safe_name(manager: Manager | None, fallback: str = "Gerente") -> str:
    value = (getattr(manager, "name", "") or "").strip()
    return value or fallback


def _format_local_dt(dt) -> str:
    if not dt:
        return "-"
    return timezone.localtime(dt).strftime("%d/%m/%Y às %H:%M")


def _dispatch_activity_label(dispatch: ManagerPersonalReminderDispatch) -> str:
    reminder = dispatch.reminder
    title = (getattr(reminder, "title", "") or "").strip()
    message = (getattr(reminder, "message_text", "") or "").strip()

    if title and message:
        return f"{title} — {message}"

    return title or message or "Atividade programada"


def _get_effective_monthly_date(reminder: ManagerPersonalReminder, year: int, month: int):
    if not reminder.day_of_month:
        return None

    last_day = calendar.monthrange(year, month)[1]
    raw_day = min(reminder.day_of_month, last_day)
    target = date(year, month, raw_day)

    # sábado -> sexta
    if target.weekday() == 5:
        target = target - timedelta(days=1)

    # domingo -> sexta
    if target.weekday() == 6:
        target = target - timedelta(days=2)

    return target


def _reminder_matches_day(reminder: ManagerPersonalReminder, day: date) -> bool:
    if not reminder.is_active:
        return False

    if reminder.start_date and day < reminder.start_date:
        return False

    if reminder.end_date and day > reminder.end_date:
        return False

    if reminder.schedule_type == ManagerPersonalReminder.SCHEDULE_DAILY:
        return True

    if reminder.schedule_type == ManagerPersonalReminder.SCHEDULE_WEEKLY:
        return reminder.weekday == day.weekday()

    if reminder.schedule_type == ManagerPersonalReminder.SCHEDULE_MONTHLY:
        effective_date = _get_effective_monthly_date(reminder, day.year, day.month)
        return effective_date == day

    return False


def _scheduled_label_for_reminder(reminder: ManagerPersonalReminder) -> str:
    if not reminder.time_of_day:
        return "--:--"
    return reminder.time_of_day.strftime("%H:%M")


def _reminder_activity_label(reminder: ManagerPersonalReminder) -> str:
    title = (reminder.title or "").strip()
    message = (reminder.message_text or "").strip()

    if title and message:
        return f"{title} — {message}"

    return title or message or "Atividade programada"



def _day_bounds(day: date):
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(
        timezone.datetime.combine(day, timezone.datetime.min.time()),
        tz,
    )
    end_dt = timezone.make_aware(
        timezone.datetime.combine(day, timezone.datetime.max.time()),
        tz,
    )
    return start_dt, end_dt


def coordinator_has_activity_for_day(coordinator: Manager, day: date) -> bool:
    manager_ids = list(
        coordinator.personal_reminder_managers.values_list("id", flat=True)
    )

    if not manager_ids:
        return False

    reminders = (
        ManagerPersonalReminder.objects
        .filter(
            manager_id__in=manager_ids,
            is_active=True,
        )
        .select_related("manager")
    )

    return any(_reminder_matches_day(reminder, day) for reminder in reminders)


def daily_action_already_sent(coordinator: Manager, day: date) -> bool:
    start_dt, end_dt = _day_bounds(day)

    return OutboundMessage.objects.filter(
        manager=coordinator,
        kind="personal_reminder_coordinator_daily_action",
        sent_at__gte=start_dt,
        sent_at__lte=end_dt,
    ).exists()
    


def notify_personal_reminder_coordinator(dispatch: ManagerPersonalReminderDispatch) -> bool:
    """
    Envia template para todos os coordenadores quando um manager confirma um personal reminder.
    Chamado depois que o dispatch vira answered.
    """
    if not dispatch or not dispatch.manager_id:
        return False

    manager = dispatch.manager

    coordinators = (
        manager.personal_reminder_coordinators
        .filter(is_personal_reminder_coordinator=True)
        .exclude(phone_e164="")
        .order_by("name")
    )

    if not coordinators.exists():
        logger.info(
            "[personal_reminder_coordinator_notice] skipped no_coordinator manager=%s dispatch=%s",
            _safe_name(manager),
            dispatch.id,
        )
        return False

    activity = _dispatch_activity_label(dispatch)
    confirmed_at = _format_local_dt(dispatch.answered_at)

    sent_any = False

    for coordinator in coordinators:
        body_params = [
            _safe_name(coordinator, "Coordenador"),
            _safe_name(manager, "Manager"),
            activity,
            confirmed_at,
        ]

        try:
            resp = send_template(
                coordinator.phone_e164,
                template_name=TEMPLATE_COORDINATOR_CONFIRMED,
                language_code="pt_BR",
                body_params=body_params,
            )

            provider_id = _extract_provider_message_id(resp)
            now = timezone.now()

            OutboundMessage.objects.create(
                manager=coordinator,
                checkin=None,
                related_question=None,
                to_phone=coordinator.phone_e164,
                provider_message_id=provider_id,
                kind="personal_reminder_coordinator_notice",
                text=(
                    f"{_safe_name(manager)} confirmou a execução da atividade:\n"
                    f"{activity}\n\n"
                    f"Confirmação: {confirmed_at}"
                ),
                sent_at=now,
                raw_response=resp,
                wa_status="sent" if provider_id else "",
                wa_sent_at=now if provider_id else None,
            )

            logger.info(
                "[personal_reminder_coordinator_notice] sent manager=%s coordinator=%s dispatch=%s provider_id=%s",
                _safe_name(manager),
                _safe_name(coordinator),
                dispatch.id,
                provider_id,
            )

            sent_any = True

        except Exception:
            logger.exception(
                "[personal_reminder_coordinator_notice] failed manager=%s coordinator=%s dispatch=%s",
                _safe_name(manager),
                _safe_name(coordinator),
                dispatch.id,
            )

    return sent_any


def get_active_personal_reminder_coordinators():
    return (
        Manager.objects
        .filter(is_personal_reminder_coordinator=True)
        .exclude(phone_e164="")
        .order_by("name")
    )


def send_coordinator_daily_action_template(
    *,
    coordinator: Manager,
    day: date | None = None,
    force: bool = False,
) -> bool:
    """
    Envia o template com botão: 'Deseja receber a relação agora?'
    O botão deve devolver payload CR:DAILY.
    """
    day = day or timezone.localdate()

    if not coordinator or not coordinator.phone_e164:
        return False

    if not getattr(coordinator, "is_personal_reminder_coordinator", False):
        return False

    managed_count = coordinator.personal_reminder_managers.count()

    if managed_count <= 0:
        logger.info(
            "[personal_reminder_daily_action] skipped no_managers coordinator=%s",
            _safe_name(coordinator),
        )
        return False

    if not force and not coordinator_has_activity_for_day(coordinator, day):
        logger.info(
            "[personal_reminder_daily_action] skipped no_activity coordinator=%s day=%s",
            _safe_name(coordinator),
            day.isoformat(),
        )
        return False

    if not force and daily_action_already_sent(coordinator, day):
        logger.info(
            "[personal_reminder_daily_action] skipped already_sent coordinator=%s day=%s",
            _safe_name(coordinator),
            day.isoformat(),
        )
        return False

    try:
        resp = send_template(
            coordinator.phone_e164,
            template_name=TEMPLATE_COORDINATOR_DAILY_ACTION,
            language_code="pt_BR",
            body_params=[
                _safe_name(coordinator, "Coordenador"),
            ],
            quick_reply_payloads=[PAYLOAD_COORDINATOR_DAILY],
        )

        provider_id = _extract_provider_message_id(resp)

        OutboundMessage.objects.create(
            manager=coordinator,
            checkin=None,
            related_question=None,
            to_phone=coordinator.phone_e164,
            provider_message_id=provider_id,
            kind="personal_reminder_coordinator_daily_action",
            text=f"Resumo de atividades programadas disponível para {day.strftime('%d/%m/%Y')}.",
            sent_at=timezone.now(),
            raw_response=resp,
            wa_status="sent" if provider_id else "",
            wa_sent_at=timezone.now() if provider_id else None,
        )

        logger.info(
            "[personal_reminder_daily_action] sent coordinator=%s day=%s managed_count=%s provider_id=%s",
            _safe_name(coordinator),
            day.isoformat(),
            managed_count,
            provider_id,
        )
        return True

    except Exception:
        logger.exception(
            "[personal_reminder_daily_action] failed coordinator=%s day=%s",
            _safe_name(coordinator),
            day.isoformat(),
        )
        return False


def build_coordinator_daily_summary_blocks(*, coordinator: Manager, day: date | None = None) -> list[tuple[Manager, str]]:
    """
    Monta 1 bloco/mensagem por manager com todas as tarefas cadastradas para o dia,
    independentemente de já ter disparado dispatch ou não.
    """
    day = day or timezone.localdate()

    managers = list(
        coordinator.personal_reminder_managers
        .all()
        .order_by("name")
    )

    if not managers:
        return []

    manager_ids = [m.id for m in managers]

    reminders = list(
        ManagerPersonalReminder.objects
        .select_related("manager")
        .filter(
            manager_id__in=manager_ids,
            is_active=True,
        )
        .order_by("manager__name", "time_of_day", "title", "id")
    )

    reminders_by_manager = {}
    for reminder in reminders:
        if not _reminder_matches_day(reminder, day):
            continue
        reminders_by_manager.setdefault(reminder.manager_id, []).append(reminder)

    # Dispatches entram só para enriquecer status, não para definir se a tarefa existe.
    dispatches = list(
        ManagerPersonalReminderDispatch.objects
        .select_related("manager", "reminder")
        .filter(
            manager_id__in=manager_ids,
            reference_date=day,
        )
    )

    dispatch_by_reminder_id = {
        d.reminder_id: d
        for d in dispatches
    }

    blocks = []

    for manager in managers:
        manager_reminders = reminders_by_manager.get(manager.id) or []

        lines = [
            f"📋 Atividades de {manager.name}",
            day.strftime("%d/%m/%Y"),
            "",
        ]

        if not manager_reminders:
            lines.append("Nenhuma atividade cadastrada para hoje.")
            blocks.append((manager, "\n".join(lines).strip()))
            continue

        for reminder in manager_reminders:
            hour = _scheduled_label_for_reminder(reminder)
            activity = _reminder_activity_label(reminder)
            dispatch = dispatch_by_reminder_id.get(reminder.id)

            if dispatch:
                if dispatch.status == "answered":
                    status_label = (
                        f"✅ Confirmada às {timezone.localtime(dispatch.answered_at).strftime('%H:%M')}"
                        if dispatch.answered_at
                        else "✅ Confirmada"
                    )
                elif dispatch.status == "pending":
                    status_label = "⏳ Enviada / pendente"
                elif dispatch.status == "sent":
                    status_label = "📨 Enviada"
                elif dispatch.status == "missed":
                    status_label = "⚠️ Expirada"
                elif dispatch.status == "failed":
                    status_label = "❌ Falhou"
                else:
                    status_label = dispatch.status or "-"
            else:
                status_label = "🗓️ Programada"

            lines.append(f"• {hour} · {activity}")
            lines.append(f"  {status_label}")

        blocks.append((manager, "\n".join(lines).strip()))

    return blocks


def build_coordinator_daily_summary_text(*, coordinator: Manager, day: date | None = None) -> str:
    """
    Mantido como fallback/debug: junta todos os blocos em uma única string.
    No envio real, usamos 1 mensagem por manager.
    """
    blocks = build_coordinator_daily_summary_blocks(
        coordinator=coordinator,
        day=day,
    )

    if not blocks:
        return "Não encontrei managers vinculados a você como coordenador."

    return "\n\n---\n\n".join(body for _, body in blocks)



def send_coordinator_daily_summary_text(*, coordinator: Manager, day: date | None = None) -> bool:
    """
    Envia 1 mensagem por manager com as tarefas cadastradas para o dia.
    Chamado depois do clique no botão CR:DAILY.
    """
    day = day or timezone.localdate()

    blocks = build_coordinator_daily_summary_blocks(
        coordinator=coordinator,
        day=day,
    )

    if not blocks:
        try:
            body = "Não encontrei managers vinculados a você como coordenador."
            resp = send_text(coordinator.phone_e164, body)
            provider_id = _extract_provider_message_id(resp)
            now = timezone.now()

            OutboundMessage.objects.create(
                manager=coordinator,
                checkin=None,
                related_question=None,
                to_phone=coordinator.phone_e164,
                provider_message_id=provider_id,
                kind="personal_reminder_coordinator_daily_summary",
                text=body,
                sent_at=now,
                raw_response=resp,
                wa_status="sent" if provider_id else "",
                wa_sent_at=now if provider_id else None,
            )
            return True
        except Exception:
            logger.exception(
                "[personal_reminder_daily_summary] failed no_blocks coordinator=%s day=%s",
                _safe_name(coordinator),
                day.isoformat(),
            )
            return False

    sent_any = False

    for manager, body in blocks:
        try:
            resp = send_text(coordinator.phone_e164, body)
            provider_id = _extract_provider_message_id(resp)
            now = timezone.now()

            OutboundMessage.objects.create(
                manager=coordinator,
                checkin=None,
                related_question=None,
                to_phone=coordinator.phone_e164,
                provider_message_id=provider_id,
                kind="personal_reminder_coordinator_daily_summary",
                text=body,
                sent_at=now,
                raw_response=resp,
                wa_status="sent" if provider_id else "",
                wa_sent_at=now if provider_id else None,
            )

            logger.info(
                "[personal_reminder_daily_summary] sent coordinator=%s manager=%s day=%s provider_id=%s",
                _safe_name(coordinator),
                _safe_name(manager),
                day.isoformat(),
                provider_id,
            )

            sent_any = True

        except Exception:
            logger.exception(
                "[personal_reminder_daily_summary] failed coordinator=%s manager=%s day=%s",
                _safe_name(coordinator),
                _safe_name(manager),
                day.isoformat(),
            )

    return sent_any

def handle_coordinator_personal_reminder_action(*, manager: Manager, reply_id: str, now=None) -> bool:
    """
    Handler do webhook para payload CR:DAILY.
    """
    rid = (reply_id or "").strip().upper()

    if rid != PAYLOAD_COORDINATOR_DAILY:
        return False

    if not manager:
        return False

    if not getattr(manager, "is_personal_reminder_coordinator", False):
        try:
            send_text(
                manager.phone_e164,
                "Você não está habilitado para receber o resumo dos avisos pessoais."
            )
        except Exception:
            logger.exception(
                "[personal_reminder_daily_summary] not_allowed_reply_failed manager=%s",
                _safe_name(manager),
            )
        return True

    return send_coordinator_daily_summary_text(
        coordinator=manager,
        day=timezone.localdate(),
    )