from __future__ import annotations

import logging
import re
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import OutboundMessage
from opscheckin.services.whatsapp import send_template
from opscheckin.services.recipients import managers_subscribed
from opscheckin.services.director_agenda_summary import (
    build_director_agenda_summary_blocks,
    build_director_agenda_summary_overview,
)


logger = logging.getLogger("opscheckin.director_agenda_summary_tick")

DIRECTOR_MANAGER_SUMMARY_TEMPLATE_NAME = getattr(
    settings,
    "WHATSAPP_TEMPLATE_AGENDA_SUMMARY_NAME",
    "agenda_summary",
)
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


def _director_manager_summary_template_enabled() -> bool:
    return _setting_bool("WHATSAPP_TEMPLATE_AGENDA_SUMMARY_ENABLED", False)


def _director_global_summary_template_enabled() -> bool:
    return _setting_bool("WHATSAPP_TEMPLATE_DIRECTOR_AGENDA_GLOBAL_SUMMARY_ACTION_ENABLED", False)


def _director_templates_enabled() -> bool:
    return (
        _director_manager_summary_template_enabled()
        and _director_global_summary_template_enabled()
    )


def _strip_manager_title_from_summary(manager_name: str, summary: str) -> str:
    text = (summary or "").strip()
    if not text:
        return ""

    lines = text.splitlines()
    if not lines:
        return text

    first = (lines[0] or "").strip()
    name = (manager_name or "").strip()

    patterns = [
        rf"^\*?{re.escape(name)}\*?$",
        rf"^👤\s*\*?{re.escape(name)}\*?$",
        rf"^📋\s*\*?{re.escape(name)}\*?$",
        rf"^1\)\s*👤\s*\*?{re.escape(name)}\*?$",
    ]

    if any(re.match(p, first, re.I) for p in patterns):
        lines = lines[1:]
        while lines and not (lines[0] or "").strip():
            lines.pop(0)

    return "\n".join(lines).strip() or text


def _build_director_template_entries(managers, blocks):
    entries = []
    block_list = list(blocks or [])

    for idx, manager in enumerate(list(managers or [])):
        raw_block = block_list[idx] if idx < len(block_list) else ""
        raw_block = (raw_block or "").strip()
        if not raw_block:
            continue

        clean_summary = _strip_manager_title_from_summary(
            getattr(manager, "name", "") or f"Manager {idx + 1}",
            raw_block,
        )

        entries.append({
            "manager": manager,
            "name": getattr(manager, "name", "") or f"Manager {idx + 1}",
            "summary": clean_summary or raw_block,
        })

    return entries


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

        if not _director_templates_enabled():
            self.stdout.write(self.style.WARNING(
                "[director_agenda_summary_tick] templates desativados; "
                f"agenda_summary={_director_manager_summary_template_enabled()} "
                f"director_agenda_global_summary_action={_director_global_summary_template_enabled()}"
            ))
            return

        blocks = build_director_agenda_summary_blocks(day=day, managers=managers)
        overview = build_director_agenda_summary_overview(day=day, managers=managers)
        entries = _build_director_template_entries(managers, blocks)

        if not entries:
            self.stdout.write(self.style.WARNING(
                "[director_agenda_summary_tick] nenhum bloco válido para template"
            ))
            return

        if dry_run:
            for i, entry in enumerate(entries, start=1):
                self.stdout.write(f"===== TEMPLATE agenda_summary #{i} =====")
                self.stdout.write(f"nome: {entry['name']}")
                self.stdout.write("resumo:")
                self.stdout.write(entry["summary"])
                self.stdout.write("")
            self.stdout.write("===== TEMPLATE director_agenda_global_summary_action =====")
            self.stdout.write("resumo:")
            self.stdout.write(overview)
            self.stdout.write("")
            return

        sent = 0

        for director in directors:
            try:
                ok_all = True

                # 1) envia uma template por manager
                for idx, entry in enumerate(entries, start=1):
                    resp_template = send_template(
                        director.phone_e164,
                        template_name=DIRECTOR_MANAGER_SUMMARY_TEMPLATE_NAME,
                        language_code=DIRECTOR_TEMPLATE_LANGUAGE,
                        body_params=[
                            entry["name"],
                            entry["summary"],
                        ],
                    )

                    _log_outbound_text(
                        manager=director,
                        body=f"[TEMPLATE:{DIRECTOR_MANAGER_SUMMARY_TEMPLATE_NAME}] {entry['name']}\n\n{entry['summary']}",
                        resp=resp_template,
                        kind="agenda_summary_director_template",
                    )

                    provider_id = _extract_provider_id(resp_template)
                    if not provider_id:
                        ok_all = False
                        logger.warning(
                            "DIRECTOR_AGENDA_TEMPLATE_MANAGER_FAILED to=%s director=%s day=%s idx=%s template=%s resp=%s",
                            director.phone_e164,
                            director.name,
                            day.isoformat(),
                            idx,
                            DIRECTOR_MANAGER_SUMMARY_TEMPLATE_NAME,
                            resp_template,
                        )
                        break

                if not ok_all:
                    continue

                # 2) envia template final com resumo geral + botão
                resp_global = send_template(
                    director.phone_e164,
                    template_name=DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME,
                    language_code=DIRECTOR_TEMPLATE_LANGUAGE,
                    body_params=[overview],
                    quick_reply_payloads=["DIR:REFRESH"],
                )

                _log_outbound_text(
                    manager=director,
                    body=f"[TEMPLATE:{DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME}] {overview}",
                    resp=resp_global,
                    kind="agenda_summary_director_global_template",
                )

                provider_id_global = _extract_provider_id(resp_global)

                if provider_id_global:
                    sent += 1
                    logger.warning(
                        "DIRECTOR_AGENDA_TEMPLATE_SENT to=%s director=%s day=%s entries=%s template_manager=%s template_global=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        len(entries),
                        DIRECTOR_MANAGER_SUMMARY_TEMPLATE_NAME,
                        DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME,
                    )
                else:
                    logger.warning(
                        "DIRECTOR_AGENDA_TEMPLATE_GLOBAL_FAILED to=%s director=%s day=%s template=%s resp=%s",
                        director.phone_e164,
                        director.name,
                        day.isoformat(),
                        DIRECTOR_GLOBAL_SUMMARY_TEMPLATE_NAME,
                        resp_global,
                    )

            except Exception as e:
                logger.exception(
                    "DIRECTOR_AGENDA_TEMPLATE_EXCEPTION to=%s director=%s day=%s err=%s",
                    director.phone_e164,
                    director.name,
                    day.isoformat(),
                    str(e),
                )

        self.stdout.write(self.style.SUCCESS(
            f"[director_agenda_summary_tick] sent={sent} managers={len(managers)} directors={len(directors)} entries={len(entries)}"
        ))