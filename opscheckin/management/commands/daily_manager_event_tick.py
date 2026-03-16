from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from opscheckin.models import (
    DailyManagerEvent,
    DailyManagerEventDispatch,
    NotificationType,
    OutboundMessage,
)
from opscheckin.services.recipients import managers_subscribed
from opscheckin.services.whatsapp import send_template


logger = logging.getLogger("opscheckin.daily_manager_event_tick")


EVENT_CODE = "farm_daily_agenda"
NOTIFICATION_CODE = "daily_meeting_reminder"

REMINDER_OFFSETS_MINUTES = [60, 10]


def _local_now():
    return timezone.localtime(timezone.now())


def _extract_provider_id(resp):
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""


def _weekday_allows_run(day):
    # segunda=0 ... sábado=5 | domingo=6
    return day.weekday() <= 5


def _fmt_hhmm(t):
    return t.strftime("%H:%M")


def _get_base_greeting(event_dt):
    return "Bom dia," if event_dt.hour < 12 else "Boa tarde,"


def _build_greeting(event_dt, *, is_reschedule=False):
    base = _get_base_greeting(event_dt)
    if is_reschedule:
        return f"*Atenção: o horário da reunião foi alterado.*\n\n{base}"
    return base


def _get_effective_event_time(event, day):
    """
    Usa override_time apenas quando override_date == hoje.
    Caso contrário, usa default_time.
    """
    if getattr(event, "override_date", None) == day and getattr(event, "override_time", None):
        return event.override_time
    return event.default_time


def _reset_past_override_if_needed(event, day):
    """
    Se ficou override de dia anterior, limpa automaticamente.
    """
    override_date = getattr(event, "override_date", None)
    if override_date and override_date < day:
        fields = []
        if getattr(event, "override_date", None) is not None:
            event.override_date = None
            fields.append("override_date")
        if getattr(event, "override_time", None) is not None:
            event.override_time = None
            fields.append("override_time")
        if hasattr(event, "last_reset_at"):
            event.last_reset_at = timezone.now()
            fields.append("last_reset_at")
        if fields:
            event.save(update_fields=fields)
            logger.warning(
                "DAILY_EVENT_OVERRIDE_RESET event=%s old_override_date=%s",
                getattr(event, "code", ""),
                override_date,
            )


def _is_due_target(*, now_local, target_dt, allowed_window_minutes):
    """
    Considera vencido se o horário alvo já chegou e ainda está dentro da janela tolerada.
    """
    diff_minutes = (now_local - target_dt).total_seconds() / 60.0
    return 0 <= diff_minutes <= allowed_window_minutes, diff_minutes


def _build_due_targets(*, now_local, event_dt, allowed_window_minutes):
    due = []

    for offset in REMINDER_OFFSETS_MINUTES:
        target_dt = event_dt - timedelta(minutes=offset)
        is_due, diff_minutes = _is_due_target(
            now_local=now_local,
            target_dt=target_dt,
            allowed_window_minutes=allowed_window_minutes,
        )
        due.append({
            "offset": offset,
            "target_dt": target_dt,
            "is_due": is_due,
            "delay_minutes": diff_minutes,
        })

    return due


def _already_sent(event, manager, day, scheduled_event_time, target_send_time):
    return DailyManagerEventDispatch.objects.filter(
        event=event,
        manager=manager,
        event_date=day,
        scheduled_event_time=scheduled_event_time,
        target_send_time=target_send_time,
    ).exists()


def _manager_has_any_dispatch_today(event, manager, day):
    return DailyManagerEventDispatch.objects.filter(
        event=event,
        manager=manager,
        event_date=day,
    ).exists()


def _manager_has_dispatch_for_other_schedule_today(event, manager, day, scheduled_event_time):
    return DailyManagerEventDispatch.objects.filter(
        event=event,
        manager=manager,
        event_date=day,
    ).exclude(
        scheduled_event_time=scheduled_event_time,
    ).exists()


def _reschedule_notice_already_sent(event, manager, day, scheduled_event_time):
    """
    Para o aviso de alteração, usamos target_send_time sintético igual ao próprio
    scheduled_event_time e status='schedule_changed'.
    """
    return DailyManagerEventDispatch.objects.filter(
        event=event,
        manager=manager,
        event_date=day,
        scheduled_event_time=scheduled_event_time,
        target_send_time=scheduled_event_time,
        status="schedule_changed",
    ).exists()


def _reserve_dispatch_slot(
    *,
    event,
    manager,
    day,
    scheduled_event_time,
    target_send_time,
    status="pending",
):
    """
    Reserva atômica do slot de envio ANTES de mandar o template.
    Isso evita duplicidade quando duas execuções entram ao mesmo tempo.
    Exige unique constraint no banco.
    """
    try:
        with transaction.atomic():
            dispatch = DailyManagerEventDispatch.objects.create(
                event=event,
                manager=manager,
                event_date=day,
                scheduled_event_time=scheduled_event_time,
                target_send_time=target_send_time,
                sent_at=timezone.now(),
                status=status,
            )
            return dispatch, True
    except IntegrityError:
        return None, False


def _log_outbound_template(*, manager, body_preview, resp, kind="daily_meeting_reminder"):
    now = timezone.now()
    provider_id = _extract_provider_id(resp)

    OutboundMessage.objects.create(
        manager=manager,
        checkin=None,
        related_question=None,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=body_preview,
        sent_at=now,
        raw_response=resp,
        wa_status=("sent" if provider_id else ""),
        wa_sent_at=(now if provider_id else None),
    )


class Command(BaseCommand):
    help = "Dispara lembretes de reunião diária para managers assinados."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--hour", type=int, default=None, help="Hora local para simulação")
        parser.add_argument("--minute", type=int, default=None, help="Minuto local para simulação")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--include-inactive", action="store_true")

    def handle(self, *args, **opts):
        now_local = _local_now()

        if opts.get("date"):
            try:
                fake_day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
                now_local = now_local.replace(year=fake_day.year, month=fake_day.month, day=fake_day.day)
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        if opts.get("hour") is not None:
            now_local = now_local.replace(hour=int(opts["hour"]), second=0, microsecond=0)
        if opts.get("minute") is not None:
            now_local = now_local.replace(minute=int(opts["minute"]), second=0, microsecond=0)
        elif opts.get("hour") is not None:
            now_local = now_local.replace(minute=0, second=0, microsecond=0)

        dry_run = opts.get("dry_run", False)
        include_inactive = opts.get("include_inactive", False)
        day = now_local.date()

        self.stdout.write(f"[daily_manager_event_tick] now_local={now_local:%Y-%m-%d %H:%M:%S}")

        if not _weekday_allows_run(day):
            self.stdout.write("[daily_manager_event_tick] domingo; nada a fazer")
            return

        event = DailyManagerEvent.objects.filter(code=EVENT_CODE).first()
        if not event:
            self.stdout.write(self.style.WARNING(
                f"[daily_manager_event_tick] evento '{EVENT_CODE}' não encontrado"
            ))
            return

        if not getattr(event, "is_active", False):
            self.stdout.write(self.style.WARNING(
                f"[daily_manager_event_tick] evento '{EVENT_CODE}' inativo"
            ))
            return

        _reset_past_override_if_needed(event, day)

        if not getattr(event, "template_enabled", False):
            self.stdout.write(self.style.WARNING(
                f"[daily_manager_event_tick] template desabilitado para evento '{EVENT_CODE}'"
            ))
            return

        template_name = (getattr(event, "template_name", "") or "").strip()
        template_language = (getattr(event, "template_language", "") or "pt_BR").strip() or "pt_BR"
        if not template_name:
            self.stdout.write(self.style.WARNING(
                f"[daily_manager_event_tick] template_name vazio para evento '{EVENT_CODE}'"
            ))
            return

        notification_type = NotificationType.objects.filter(code=NOTIFICATION_CODE, is_active=True).first()
        if not notification_type:
            self.stdout.write(self.style.WARNING(
                f"[daily_manager_event_tick] NotificationType '{NOTIFICATION_CODE}' não encontrado/ativo"
            ))
            return

        scheduled_event_time = _get_effective_event_time(event, day)
        event_dt = timezone.make_aware(
            datetime.combine(day, scheduled_event_time),
            timezone.get_current_timezone(),
        )

        allowed_window_minutes = int(getattr(event, "allowed_window_minutes", 15) or 15)

        due_targets = _build_due_targets(
            now_local=now_local,
            event_dt=event_dt,
            allowed_window_minutes=allowed_window_minutes,
        )

        self.stdout.write(
            "[daily_manager_event_tick] "
            f"event_time={event_dt:%H:%M} "
            f"due_targets={[(x['offset'], x['target_dt'].strftime('%H:%M'), x['is_due']) for x in due_targets]}"
        )

        managers = list(
            managers_subscribed(
                NOTIFICATION_CODE,
                include_inactive=include_inactive,
            ).order_by("name")
        )

        if not managers:
            self.stdout.write("[daily_manager_event_tick] nenhum manager assinado/ativo")
            return

        meeting_time_str = _fmt_hhmm(scheduled_event_time)
        meeting_name = (getattr(event, "name", "") or "AGENDA DIÁRIA DA FAZENDA").strip()
        meet_link = (getattr(event, "meet_link", "") or "").strip()

        normal_greeting = _build_greeting(event_dt, is_reschedule=False)
        changed_greeting = _build_greeting(event_dt, is_reschedule=True)

        normal_preview = (
            f"Lembrete de reunião diária da fazenda.\n\n"
            f"{normal_greeting}\n\n"
            f"Segue o link para a reunião das {meeting_time_str} horas - {meeting_name}.\n\n"
            f"Link da reunião:\n{meet_link}\n\n"
            f"Mensagem automática do sistema OpsCheckin."
        )

        changed_preview = (
            f"Lembrete de reunião diária da fazenda.\n\n"
            f"{changed_greeting}\n\n"
            f"Segue o link para a reunião das {meeting_time_str} horas - {meeting_name}.\n\n"
            f"Link da reunião:\n{meet_link}\n\n"
            f"Mensagem automática do sistema OpsCheckin."
        )

        if dry_run:
            self.stdout.write("===== DRY RUN =====")
            self.stdout.write(f"template_name={template_name}")
            self.stdout.write(f"template_language={template_language}")
            self.stdout.write(f"meeting_time={meeting_time_str}")
            self.stdout.write(f"meeting_name={meeting_name}")
            self.stdout.write(f"meet_link={meet_link}")
            self.stdout.write(f"allowed_window_minutes={allowed_window_minutes}")
            self.stdout.write(f"managers={len(managers)}")
            self.stdout.write("")

            for m in managers:
                has_changed_schedule = _manager_has_dispatch_for_other_schedule_today(
                    event=event,
                    manager=m,
                    day=day,
                    scheduled_event_time=scheduled_event_time,
                )
                changed_notice_sent = _reschedule_notice_already_sent(
                    event=event,
                    manager=m,
                    day=day,
                    scheduled_event_time=scheduled_event_time,
                )

                self.stdout.write(
                    f"- {m.name} ({m.phone_e164}) | "
                    f"has_changed_schedule={has_changed_schedule} | "
                    f"changed_notice_sent={changed_notice_sent}"
                )

                for item in due_targets:
                    already = _already_sent(
                        event=event,
                        manager=m,
                        day=day,
                        scheduled_event_time=scheduled_event_time,
                        target_send_time=item["target_dt"].time(),
                    )
                    self.stdout.write(
                        f"    offset={item['offset']} "
                        f"target={item['target_dt']:%H:%M} "
                        f"is_due={item['is_due']} "
                        f"already_sent={already}"
                    )
            return

        sent = 0
        skipped_already = 0
        failed = 0
        changed_sent = 0

        for manager in managers:
            try:
                # -------------------------------------------------
                # 1) Aviso imediato de alteração de horário
                # -------------------------------------------------
                has_dispatch_today = _manager_has_any_dispatch_today(
                    event=event,
                    manager=manager,
                    day=day,
                )

                has_dispatch_for_other_schedule = _manager_has_dispatch_for_other_schedule_today(
                    event=event,
                    manager=manager,
                    day=day,
                    scheduled_event_time=scheduled_event_time,
                )

                should_send_schedule_changed_notice = (
                    has_dispatch_today
                    and has_dispatch_for_other_schedule
                    and not _reschedule_notice_already_sent(
                        event=event,
                        manager=manager,
                        day=day,
                        scheduled_event_time=scheduled_event_time,
                    )
                )

                if should_send_schedule_changed_notice:
                    dispatch, reserved = _reserve_dispatch_slot(
                        event=event,
                        manager=manager,
                        day=day,
                        scheduled_event_time=scheduled_event_time,
                        target_send_time=scheduled_event_time,  # marcador sintético
                        status="schedule_changed",
                    )

                    if reserved:
                        resp = send_template(
                            manager.phone_e164,
                            template_name=template_name,
                            language_code=template_language,
                            body_params=[
                                changed_greeting,
                                meeting_time_str,
                                meeting_name,
                                meet_link,
                            ],
                        )

                        provider_id = _extract_provider_id(resp)

                        dispatch.provider_message_id = provider_id
                        dispatch.status = "schedule_changed"
                        dispatch.sent_at = timezone.now()
                        dispatch.save(update_fields=["provider_message_id", "status", "sent_at"])

                        _log_outbound_template(
                            manager=manager,
                            body_preview=changed_preview,
                            resp=resp,
                            kind="daily_meeting_reminder_changed",
                        )

                        changed_sent += 1
                        logger.warning(
                            "DAILY_EVENT_SCHEDULE_CHANGED_SENT manager=%s phone=%s event=%s day=%s new_meeting_time=%s provider_id=%s",
                            manager.name,
                            manager.phone_e164,
                            event.code,
                            day.isoformat(),
                            meeting_time_str,
                            provider_id,
                        )
                    else:
                        skipped_already += 1
                        logger.warning(
                            "DAILY_EVENT_SCHEDULE_CHANGED_ALREADY_RESERVED manager=%s phone=%s event=%s day=%s new_meeting_time=%s",
                            manager.name,
                            manager.phone_e164,
                            event.code,
                            day.isoformat(),
                            meeting_time_str,
                        )

                # -------------------------------------------------
                # 2) Lembretes normais de 60 e 10 minutos
                # -------------------------------------------------
                for item in due_targets:
                    if not item["is_due"]:
                        continue

                    target_send_time = item["target_dt"].time()

                    dispatch, reserved = _reserve_dispatch_slot(
                        event=event,
                        manager=manager,
                        day=day,
                        scheduled_event_time=scheduled_event_time,
                        target_send_time=target_send_time,
                        status="pending",
                    )

                    if not reserved:
                        skipped_already += 1
                        logger.warning(
                            "DAILY_EVENT_ALREADY_RESERVED manager=%s phone=%s event=%s day=%s meeting_time=%s offset=%s target=%s",
                            manager.name,
                            manager.phone_e164,
                            event.code,
                            day.isoformat(),
                            meeting_time_str,
                            item["offset"],
                            item["target_dt"].strftime("%H:%M"),
                        )
                        continue

                    resp = send_template(
                        manager.phone_e164,
                        template_name=template_name,
                        language_code=template_language,
                        body_params=[
                            normal_greeting,
                            meeting_time_str,
                            meeting_name,
                            meet_link,
                        ],
                    )

                    provider_id = _extract_provider_id(resp)

                    dispatch.provider_message_id = provider_id
                    dispatch.status = "sent" if provider_id else "unknown"
                    dispatch.sent_at = timezone.now()
                    dispatch.save(update_fields=["provider_message_id", "status", "sent_at"])

                    _log_outbound_template(
                        manager=manager,
                        body_preview=normal_preview,
                        resp=resp,
                        kind="daily_meeting_reminder",
                    )

                    sent += 1
                    logger.warning(
                        "DAILY_EVENT_SENT manager=%s phone=%s event=%s day=%s meeting_time=%s offset=%s target=%s provider_id=%s",
                        manager.name,
                        manager.phone_e164,
                        event.code,
                        day.isoformat(),
                        meeting_time_str,
                        item["offset"],
                        item["target_dt"].strftime("%H:%M"),
                        provider_id,
                    )

            except Exception as e:
                failed += 1
                logger.exception(
                    "DAILY_EVENT_SEND_FAILED manager=%s phone=%s event=%s day=%s err=%s",
                    getattr(manager, "name", ""),
                    getattr(manager, "phone_e164", ""),
                    getattr(event, "code", ""),
                    day.isoformat(),
                    str(e),
                )

        self.stdout.write(self.style.SUCCESS(
            f"[daily_manager_event_tick] sent={sent} changed_sent={changed_sent} skipped_already={skipped_already} failed={failed} managers={len(managers)}"
        ))