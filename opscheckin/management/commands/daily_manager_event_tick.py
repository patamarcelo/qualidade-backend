from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
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


def _local_now():
    return timezone.localtime(timezone.now())


def _local_today():
    return _local_now().date()


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


def _get_greeting(event_dt):
    return "Bom dia," if event_dt.hour < 12 else "Boa tarde,"


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


def _should_send_now(*, now_local, event_dt):
    remaining_minutes = (event_dt - now_local).total_seconds() / 60.0

    if remaining_minutes < 0:
        return False, remaining_minutes

    if 50 <= remaining_minutes <= 90:
        return True, remaining_minutes

    return False, remaining_minutes


def _already_sent(event, manager, day, scheduled_event_time, target_send_time):
    return DailyManagerEventDispatch.objects.filter(
        event=event,
        manager=manager,
        event_date=day,
        scheduled_event_time=scheduled_event_time,
        target_send_time=target_send_time,
    ).exists()


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

        offset_minutes = int(getattr(event, "reminder_offset_minutes", 60) or 60)
        allowed_window_minutes = int(getattr(event, "allowed_window_minutes", 90) or 90)
        
        
        send_target_dt = event_dt - timedelta(minutes=60)

        should_send, remaining_minutes = _should_send_now(
            now_local=now_local,
            event_dt=event_dt,
        )
        

        self.stdout.write(
            "[daily_manager_event_tick] "
            f"event_time={event_dt:%H:%M} "
            f"send_target={send_target_dt:%H:%M} "
            f"remaining_minutes={remaining_minutes:.1f} "
            f"should_send={should_send}"
        )

        if not should_send:
            return

        managers = list(
            managers_subscribed(
                NOTIFICATION_CODE,
                include_inactive=include_inactive,
            ).order_by("name")
        )
        
    

        if not managers:
            self.stdout.write("[daily_manager_event_tick] nenhum manager assinado/ativo")
            return

        greeting = _get_greeting(event_dt)
        meeting_time_str = _fmt_hhmm(scheduled_event_time)
        meeting_name = (getattr(event, "name", "") or "AGENDA DIÁRIA DA FAZENDA").strip()
        meet_link = (getattr(event, "meet_link", "") or "").strip()

        preview = (
            f"Lembrete de reunião diária da fazenda.\n\n"
            f"{greeting}\n\n"
            f"Segue o link para a reunião das {meeting_time_str} horas - {meeting_name}.\n\n"
            f"Link da reunião:\n{meet_link}\n\n"
            f"Mensagem automática do sistema OpsCheckin."
        )

        if dry_run:
            self.stdout.write("===== DRY RUN =====")
            self.stdout.write(f"template_name={template_name}")
            self.stdout.write(f"template_language={template_language}")
            self.stdout.write(f"greeting={greeting}")
            self.stdout.write(f"meeting_time={meeting_time_str}")
            self.stdout.write(f"meeting_name={meeting_name}")
            self.stdout.write(f"meet_link={meet_link}")
            self.stdout.write(f"managers={len(managers)}")
            self.stdout.write("")
            for m in managers:
                already = _already_sent(
                    event=event,
                    manager=m,
                    day=day,
                    scheduled_event_time=scheduled_event_time,
                    target_send_time=send_target_dt.time(),
                )
                self.stdout.write(
                    f"- {m.name} ({m.phone_e164}) | already_sent={already}"
                )
            return

        sent = 0
        skipped_already = 0
        failed = 0

        for manager in managers:
            try:
                if _already_sent(
                    event=event,
                    manager=manager,
                    day=day,
                    scheduled_event_time=scheduled_event_time,
                    target_send_time=send_target_dt.time(),
                ):
                    skipped_already += 1
                    logger.warning(
                        "DAILY_EVENT_ALREADY_SENT manager=%s phone=%s event=%s day=%s time=%s",
                        manager.name,
                        manager.phone_e164,
                        event.code,
                        day.isoformat(),
                        meeting_time_str,
                    )
                    continue

                resp = send_template(
                    manager.phone_e164,
                    template_name=template_name,
                    language_code=template_language,
                    body_params=[
                        greeting,
                        meeting_time_str,
                        meeting_name,
                        meet_link,
                    ],
                )

                provider_id = _extract_provider_id(resp)

                DailyManagerEventDispatch.objects.create(
                    event=event,
                    manager=manager,
                    event_date=day,
                    scheduled_event_time=scheduled_event_time,
                    target_send_time=send_target_dt.time(),
                    sent_at=timezone.now(),
                    provider_message_id=provider_id,
                    status=("sent" if provider_id else "unknown"),
                )

                _log_outbound_template(
                    manager=manager,
                    body_preview=preview,
                    resp=resp,
                    kind="daily_meeting_reminder",
                )

                sent += 1
                logger.warning(
                    "DAILY_EVENT_SENT manager=%s phone=%s event=%s day=%s meeting_time=%s provider_id=%s",
                    manager.name,
                    manager.phone_e164,
                    event.code,
                    day.isoformat(),
                    meeting_time_str,
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
            f"[daily_manager_event_tick] sent={sent} skipped_already={skipped_already} failed={failed} managers={len(managers)}"
        ))