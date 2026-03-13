from __future__ import annotations

import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import OutboundMessage
from opscheckin.services.whatsapp import send_text, send_buttons
from opscheckin.services.recipients import managers_subscribed
from opscheckin.services.director_agenda_summary import (
    build_director_agenda_summary_blocks,
    build_director_agenda_summary_overview,
)


logger = logging.getLogger("opscheckin.director_agenda_summary_tick")


def _local_today():
    return timezone.localdate()


def _extract_provider_id(resp):
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""


def _log_outbound_text(*, manager, body, resp, kind="agenda_summary_director"):
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

        director_qs = managers_subscribed(
            "agenda_summary_director",
            include_inactive=include_inactive,
        ).order_by("name")

        managers = list(manager_qs)
        directors = list(director_qs)

        if not managers:
            self.stdout.write("[director_agenda_summary_tick] nenhum manager inscrito em agenda_prompt")
            return

        if not directors:
            self.stdout.write("[director_agenda_summary_tick] nenhum destinatário inscrito em agenda_summary_director")
            return

        blocks = build_director_agenda_summary_blocks(day=day, managers=managers)
        overview = build_director_agenda_summary_overview(day=day, managers=managers)
        action_body = "Deseja receber as agendas atualizadas?"

        if dry_run:
            for i, block in enumerate(blocks, start=1):
                self.stdout.write(f"===== BLOCO {i} =====")
                self.stdout.write(block)
                self.stdout.write("")
            self.stdout.write("===== RESUMO GERAL =====")
            self.stdout.write(overview)
            self.stdout.write("")
            self.stdout.write("===== TEXTO DOS BOTÕES =====")
            self.stdout.write(action_body)
            return

        sent = 0

        for director in directors:
            try:
                ok_all = True

                # 1) envia uma mensagem por manager
                for idx, block in enumerate(blocks, start=1):
                    resp_text = send_text(director.phone_e164, block)

                    _log_outbound_text(
                        manager=director,
                        body=block,
                        resp=resp_text,
                        kind="agenda_summary_director",
                    )

                    provider_id_text = _extract_provider_id(resp_text)
                    if not provider_id_text:
                        ok_all = False
                        logger.warning(
                            "DIRECTOR_AGENDA_SUMMARY_BLOCK_FAILED to=%s manager=%s day=%s block=%s resp=%s",
                            director.phone_e164,
                            director.name,
                            day.isoformat(),
                            idx,
                            resp_text,
                        )
                        break

                if not ok_all:
                    continue

                # 2) envia resumo geral separado
                resp_overview = send_text(director.phone_e164, overview)

                _log_outbound_text(
                    manager=director,
                    body=overview,
                    resp=resp_overview,
                    kind="agenda_summary_director_overview",
                )

                provider_id_overview = _extract_provider_id(resp_overview)
                if not provider_id_overview:
                    logger.warning(
                        "DIRECTOR_AGENDA_SUMMARY_OVERVIEW_FAILED to=%s manager=%s day=%s resp=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        resp_overview,
                    )
                    continue

                # 3) envia ação curta com botão
                resp_buttons = send_buttons(
                    director.phone_e164,
                    body=action_body,
                    buttons=[
                        {"id": "DIR:REFRESH", "title": "🔄 Atualizar agora"},
                    ],
                )

                _log_outbound_text(
                    manager=director,
                    body=action_body,
                    resp=resp_buttons,
                    kind="agenda_summary_director_actions",
                )

                provider_id_buttons = _extract_provider_id(resp_buttons)

                if provider_id_buttons:
                    sent += 1
                    logger.warning(
                        "DIRECTOR_AGENDA_SUMMARY_SENT to=%s manager=%s day=%s blocks=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        len(blocks),
                    )
                else:
                    logger.warning(
                        "DIRECTOR_AGENDA_SUMMARY_BUTTONS_FAILED to=%s manager=%s day=%s resp=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        resp_buttons,
                    )

            except Exception as e:
                logger.exception(
                    "DIRECTOR_AGENDA_SUMMARY_EXCEPTION to=%s manager=%s day=%s err=%s",
                    director.phone_e164,
                    director.name,
                    day.isoformat(),
                    str(e),
                )

        self.stdout.write(self.style.SUCCESS(
            f"[director_agenda_summary_tick] sent={sent} managers={len(managers)} directors={len(directors)} blocks={len(blocks)}"
        ))