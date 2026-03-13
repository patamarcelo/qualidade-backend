from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import OutboundMessage
from opscheckin.services.whatsapp import send_template
from opscheckin.services.recipients import managers_subscribed


logger = logging.getLogger("opscheckin.director_agenda_summary_tick")

DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME = getattr(
    settings,
    "WHATSAPP_TEMPLATE_DIRECTOR_AGENDA_GLOBAL_SUMMARY_ACTION_NAME",
    "director_agenda_global_summary_action",
)
DIRECTOR_TEMPLATE_LANGUAGE = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR")


def _local_today():
    return timezone.localdate()


def _extract_provider_id(resp):
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""


def _setting_bool(name: str, default: bool = False) -> bool:
    return bool(getattr(settings, name, default))


def _director_global_summary_template_enabled() -> bool:
    return _setting_bool("WHATSAPP_TEMPLATE_DIRECTOR_AGENDA_GLOBAL_SUMMARY_ACTION_ENABLED", False)


def _log_outbound_text(*, manager, body, resp, kind="agenda_summary_director_action_template"):
    now = timezone.now()
    provider_id = _extract_provider_id(resp)

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
    help = "Envia aos diretores apenas o template com botão para solicitar as agendas atualizadas."

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

        directors = list(
            managers_subscribed(
                "agenda_summary_director",
                include_inactive=include_inactive,
            ).order_by("name")
        )

        if not directors:
            self.stdout.write("[director_agenda_summary_tick] nenhum destinatário inscrito em agenda_summary_director")
            return

        if not _director_global_summary_template_enabled():
            self.stdout.write(self.style.WARNING(
                "[director_agenda_summary_tick] template director_agenda_global_summary_action desativado"
            ))
            return

        day_br = day.strftime("%d/%m/%Y")
        body_text = f"As agendas de {day_br} estão disponíveis para consulta."

        if dry_run:
            self.stdout.write("===== TEMPLATE director_agenda_global_summary_action =====")
            self.stdout.write(f"body param resumo: {body_text}")
            self.stdout.write("quick_reply_payload: DIR:REFRESH")
            return

        sent = 0

        for director in directors:
            try:
                resp_template = send_template(
                    director.phone_e164,
                    template_name=DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME,
                    language_code=DIRECTOR_TEMPLATE_LANGUAGE,
                    body_params=[body_text],
                    quick_reply_payloads=["DIR:REFRESH"],
                )

                _log_outbound_text(
                    manager=director,
                    body=f"[TEMPLATE:{DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME}] {body_text}",
                    resp=resp_template,
                    kind="agenda_summary_director_action_template",
                )

                provider_id = _extract_provider_id(resp_template)

                if provider_id:
                    sent += 1
                    logger.warning(
                        "DIRECTOR_AGENDA_ACTION_TEMPLATE_SENT to=%s director=%s day=%s template=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME,
                    )
                else:
                    logger.warning(
                        "DIRECTOR_AGENDA_ACTION_TEMPLATE_FAILED to=%s director=%s day=%s template=%s resp=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME,
                        resp_template,
                    )

            except Exception as e:
                logger.exception(
                    "DIRECTOR_AGENDA_ACTION_TEMPLATE_EXCEPTION to=%s director=%s day=%s err=%s",
                    director.phone_e164,
                    director.name,
                    day.isoformat(),
                    str(e),
                )

        self.stdout.write(self.style.SUCCESS(
            f"[director_agenda_summary_tick] sent={sent} directors={len(directors)}"
        ))