from __future__ import annotations

import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import OutboundMessage
from opscheckin.services.whatsapp import send_text, send_buttons
from opscheckin.services.recipients import managers_subscribed
from opscheckin.services.director_agenda_summary import build_director_agenda_summary


logger = logging.getLogger("opscheckin.director_agenda_summary_tick")


def _local_today():
    return timezone.localdate()


def _log_outbound_text(*, manager, body, resp, kind="agenda_summary_director"):
    now = timezone.now()
    provider_id = ""
    try:
        provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        pass

    OutboundMessage.objects.create(
        manager=manager,
        checkin=None,
        related_question=None,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=body,
        sent_at=now,
        raw_response=resp,
        wa_status=("sent" if provider_id else ""),
        wa_sent_at=(now if provider_id else None),
    )


class Command(BaseCommand):
    help = "Envia aos diretores o resumo consolidado das agendas do dia."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        day = _local_today()
        if opts.get("date"):
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        include_inactive = opts.get("include_inactive", False)
        dry_run = opts.get("dry_run", False)

        manager_qs = managers_subscribed(
            "agenda_prompt",
            include_inactive=include_inactive,
        ).order_by("name")
        
        director_qs = managers_subscribed("agenda_summary_director", include_inactive=include_inactive)

        managers = list(manager_qs)
        directors = list(director_qs)

        if not managers:
            self.stdout.write("[director_agenda_summary_tick] nenhum manager inscrito em agenda_prompt")
            return

        if not directors:
            self.stdout.write("[director_agenda_summary_tick] nenhum destinatário inscrito em agenda_summary_director")
            return

        body = build_director_agenda_summary(day=day, managers=managers)

        if dry_run:
            self.stdout.write(body)
            return

        sent = 0
        for director in directors:
            resp = send_buttons(
                director.phone_e164,
                body=body,
                buttons=[
                    {"id": "DIR:REFRESH", "title": "🔄 Atualizar agendas"},
                ],
            )

            _log_outbound_text(
                manager=director,
                body=body,
                resp=resp,
                kind="agenda_summary_director",
            )

            provider_id = ""
            try:
                provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
            except Exception:
                pass

            if provider_id:
                sent += 1
                logger.warning(
                "DIRECTOR_AGENDA_SUMMARY_SENT to=%s manager=%s day=%s",
                director.phone_e164,
                director.name,
                day.isoformat(),
            )
            else:
                logger.warning(
                    "DIRECTOR_AGENDA_SUMMARY_FAILED to=%s manager=%s day=%s resp=%s",
                    director.phone_e164,
                    director.name,
                    day.isoformat(),
                    resp,
                )

        self.stdout.write(self.style.SUCCESS(
            f"[director_agenda_summary_tick] sent={sent} managers={len(managers)} directors={len(directors)}"
        ))