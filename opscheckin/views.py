import os
import re
import json
import hmac
import hashlib
import logging
import tempfile

import requests
from openai import OpenAI

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction

from .models import (
    Manager,
    DailyCheckin,
    OutboundQuestion,
    InboundMessage,
    OutboundMessage,
)

from opscheckin.services.whatsapp import send_buttons, send_text, send_list

logger = logging.getLogger("opscheckin.whatsapp")

# mínimo “anti-vazio” p/ considerar que veio algo (a validação real é pelo parse)
MIN_AGENDA_CHARS = 10
MAX_AUDIO_SECONDS = 300  # 5 minutos


# =========================
# COMANDOS POR TEXTO
# =========================

CMD_DONE = re.compile(r"^(feito|done)\s+(\d{1,3})\s*$", re.I)
CMD_SKIP = re.compile(r"^(pular|skip|desmarcar|reabrir)\s+(\d{1,3})\s*$", re.I)
CMD_REMOVE = re.compile(r"^(remover|delete)\s+(\d{1,3})\s*$", re.I)
CMD_EDIT = re.compile(r"^(editar|edit)\s+(\d{1,3})\s*[:\-]\s*(.+)$", re.I)
CMD_ADD1 = re.compile(r"^\+\s*(.+)$", re.I)
CMD_ADD2 = re.compile(r"^(adicionar|add)\s*[:\-]\s*(.+)$", re.I)
CMD_LIST = re.compile(r"^(listar|status|lista)\s*$", re.I)

WA_LIST_MAX_ROWS = 10
WA_CONFIRM_FIXED_ROWS = 1  # AC:OK


def _trim_list_sections(sections, max_rows=WA_LIST_MAX_ROWS):
    total = 0
    out = []

    for section in sections:
        rows = section.get("rows") or []
        room = max_rows - total
        if room <= 0:
            break

        clipped = rows[:room]
        if not clipped:
            continue

        out.append({
            **section,
            "rows": clipped,
        })
        total += len(clipped)

    return out


def _mark_inbound_processed(inbound, now, *, linked_question=None):
    fields = ["processed", "processed_at"]
    inbound.processed = True
    inbound.processed_at = now

    if linked_question is not None:
        inbound.linked_question = linked_question
        fields.append("linked_question")

    inbound.save(update_fields=fields)


def _build_agenda_bulk_header(action: str, changed: list[str], already: list[int], not_found: list[int]) -> str:
    lines = []

    if changed:
        if action == "done":
            lines.append(f"✅ {len(changed)} item(ns) concluído(s):")
        elif action == "undo":
            lines.append(f"↩️ {len(changed)} item(ns) reaberto(s):")
        elif action == "remove":
            lines.append(f"🗑️ {len(changed)} item(ns) removido(s):")

        lines.extend(changed[:12])
        if len(changed) > 12:
            lines.append("...")

    if already:
        lines.append("")
        if action == "done":
            lines.append("Já estavam concluídos: " + ", ".join(str(x) for x in already))
        elif action == "undo":
            lines.append("Já estavam em aberto: " + ", ".join(str(x) for x in already))
        elif action == "remove":
            lines.append("Já não exigiam ação: " + ", ".join(str(x) for x in already))

    if not_found:
        lines.append("")
        lines.append("Não encontrados: " + ", ".join(str(x) for x in not_found))

    return "\n".join(x for x in lines if x is not None).strip()


def _parse_agenda_selection_input(raw_value: str):
    """
    Interpreta a resposta do usuário no modo de ação pendente da agenda.

    Retornos possíveis:
      {"mode": "empty"}
      {"mode": "single_number", "numbers": [3]}
      {"mode": "multi_number", "numbers": [3, 4, 5]}
      {"mode": "text", "text": "irrigação"}
      {"mode": "invalid_mixed", "raw": "..."}
    """
    raw = (raw_value or "").strip()
    if not raw:
        return {"mode": "empty"}

    normalized = raw.replace("\r", "\n")
    normalized = normalized.replace(",", " ")
    normalized = normalized.replace(";", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if re.fullmatch(r"\d{1,3}(?:\s+\d{1,3})*", normalized):
        nums = [int(x) for x in normalized.split() if x.isdigit()]

        seen = set()
        ordered = []
        for n in nums:
            if n in seen:
                continue
            seen.add(n)
            ordered.append(n)

        if len(ordered) == 1:
            return {"mode": "single_number", "numbers": ordered}

        return {"mode": "multi_number", "numbers": ordered}

    if re.search(r"\d", raw) and not re.fullmatch(r"\d{1,3}", raw):
        return {"mode": "invalid_mixed", "raw": raw}

    return {"mode": "text", "text": raw}


def _wa_row_title(idx: int, text: str, prefix: str = "") -> str:
    raw = f"{prefix}{idx}) {(text or '').strip()}".strip()
    return raw[:24].rstrip()


def _wa_row_desc(text: str) -> str:
    s = (text or "").strip()
    return (s[:72] + "…") if len(s) > 72 else s


def _agenda_reply_text(checkin):
    from .models import AgendaItem

    items = AgendaItem.objects.filter(checkin=checkin).order_by("idx")
    if not items.exists():
        return "Ainda não tenho itens de agenda para hoje."

    lines = []
    for it in items:
        mark = "✅" if it.status == "done" else ("⛔" if it.status == "skip" else "⏳")
        lines.append(f"{mark} {it.idx}) {it.text}")

    return "Agenda de hoje:\n" + "\n".join(lines)


def _send_agenda_snapshot(manager, checkin, header: str = "") -> bool:
    """
    Envia a agenda consolidada com ícones de status.
    Nunca levanta exceção para não quebrar o webhook.
    """
    try:
        body = _agenda_reply_text(checkin)
        if header:
            body = f"{header}\n\n{body}"
        send_text(manager.phone_e164, body)
        return True
    except Exception:
        logger.exception(
            "SEND_AGENDA_SNAPSHOT_FAILED manager=%s checkin_id=%s",
            getattr(manager, "name", ""),
            getattr(checkin, "id", None),
        )
        return False


def _send_agenda_action_menu(manager, checkin):
    body = (
        "O que você quer fazer agora na agenda?\n\n"
        "Se quiser adicionar um item, envie:\n"
        "+ texto do item\n\n"
        "Ou selecione uma das opções abaixo:"
    )

    resp = send_buttons(
        manager.phone_e164,
        body=body,
        buttons=[
            {"id": "AM:MENU:DONE", "title": "✅ Concluir"},
            {"id": "AM:MENU:UNDO", "title": "↩️ Desmarcar"},
            {"id": "AM:MENU:REMOVE", "title": "🗑️ Remover"},
        ],
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=checkin,
        body=body,
        resp=resp,
        kind="agenda_actions",
    )

    return True


def _set_agenda_pending_action(checkin, action: str, now):
    """
    Guarda um estado leve de ação pendente sem precisar criar model novo.
    Usa OutboundQuestion com step próprio e sem sent_at para não interferir
    no vínculo normal das perguntas pendentes.
    """
    OutboundQuestion.objects.filter(
        checkin=checkin,
        step="AGENDA_ACTION",
        status="pending",
        answered_at__isnull=True,
    ).update(status="answered", answered_at=now, answer_text="superseded")

    return OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA_ACTION",
        scheduled_for=now,
        status="pending",
        prompt_text=(action or "").strip().lower(),
        answer_text="",
    )


def _get_agenda_pending_action(checkin):
    q = (
        OutboundQuestion.objects.filter(
            checkin=checkin,
            step="AGENDA_ACTION",
            status="pending",
            answered_at__isnull=True,
        )
        .order_by("-id")
        .first()
    )
    if not q:
        return None
    return (q.prompt_text or "").strip().lower() or None


def _clear_agenda_pending_action(checkin, now):
    OutboundQuestion.objects.filter(
        checkin=checkin,
        step="AGENDA_ACTION",
        status="pending",
        answered_at__isnull=True,
    ).update(status="answered", answered_at=now, answer_text="resolved")


def _normalize_agenda_search_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _find_agenda_matches_by_number_or_text(checkin, raw_value: str):
    from .models import AgendaItem

    value = (raw_value or "").strip()
    if not value:
        return []

    if re.fullmatch(r"\d{1,3}", value):
        idx = int(value)
        item = AgendaItem.objects.filter(checkin=checkin, idx=idx).first()
        return [item] if item else []

    q = _normalize_agenda_search_text(value)
    if len(q) < 2:
        return []

    items = list(AgendaItem.objects.filter(checkin=checkin).order_by("idx"))

    exact = []
    contains = []

    for it in items:
        txt = _normalize_agenda_search_text(it.text)
        if txt == q:
            exact.append(it)
        elif q in txt:
            contains.append(it)

    return exact if exact else contains


def _send_agenda_pending_action_prompt(manager, checkin, action: str, now):
    _set_agenda_pending_action(checkin, action, now)

    if action == "done":
        body = (
            "Me diga o número ou parte do nome do item que foi concluído.\n"
            "Você pode enviar um ou vários números.\n\n"
            "Ex.:\n"
            "3\n"
            "ou\n"
            "3 4 5"
        )
    elif action == "undo":
        body = (
            "Me diga o número ou parte do nome do item para desmarcar.\n"
            "Você pode enviar um ou vários números.\n\n"
            "Ex.:\n"
            "2\n"
            "ou\n"
            "2 4 6"
        )
    elif action == "remove":
        body = (
            "Me diga o número ou parte do nome do item para remover.\n"
            "Você pode enviar um ou vários números.\n\n"
            "Ex.:\n"
            "5\n"
            "ou\n"
            "5 7"
        )
    else:
        return False

    send_text(manager.phone_e164, body)
    return True


def _handle_agenda_pending_action_text(manager, checkin, text, now):
    action = _get_agenda_pending_action(checkin)
    if not action:
        return False

    from .models import AgendaItem

    raw = (text or "").strip()
    parsed = _parse_agenda_selection_input(raw)

    logger.warning(
        "AGENDA_PENDING_ACTION_INPUT manager=%s checkin_id=%s action=%s raw=%r parsed=%s",
        getattr(manager, "name", ""),
        getattr(checkin, "id", None),
        action,
        raw,
        parsed,
    )

    if parsed["mode"] == "empty":
        send_text(
            manager.phone_e164,
            "Responda com o número da agenda, vários números, ou parte do nome do item."
        )
        return True

    if parsed["mode"] == "invalid_mixed":
        send_text(
            manager.phone_e164,
            "Não consegui interpretar essa resposta.\n"
            "Envie apenas números (ex.: 3 ou 3 4 5) ou apenas parte do nome do item."
        )
        return True

    if parsed["mode"] in ("single_number", "multi_number"):
        numbers = parsed["numbers"] or []
        if not numbers:
            send_text(
                manager.phone_e164,
                "Não consegui identificar os números. Tente novamente."
            )
            return True

        items = list(
            AgendaItem.objects
            .filter(checkin=checkin, idx__in=numbers)
            .order_by("idx")
        )
        by_idx = {it.idx: it for it in items}

        not_found = []
        changed = []
        already = []

        for idx in numbers:
            it = by_idx.get(idx)
            if not it:
                not_found.append(idx)
                continue

            if action == "done":
                if it.status == "done":
                    already.append(idx)
                    continue
                it.status = "done"
                it.done_at = now
                it.save(update_fields=["status", "done_at"])
                changed.append(f"{it.idx}) {it.text}")

            elif action == "undo":
                if it.status == "open":
                    already.append(idx)
                    continue
                it.status = "open"
                it.done_at = None
                it.save(update_fields=["status", "done_at"])
                changed.append(f"{it.idx}) {it.text}")

            elif action == "remove":
                label = f"{it.idx}) {it.text}"
                it.delete()
                changed.append(label)

            else:
                return False

        if not changed and not not_found and already:
            if action == "done":
                send_text(
                    manager.phone_e164,
                    "Todos esses itens já estavam concluídos. Me envie outros números."
                )
            elif action == "undo":
                send_text(
                    manager.phone_e164,
                    "Todos esses itens já estavam em aberto. Me envie outros números."
                )
            else:
                send_text(
                    manager.phone_e164,
                    "Não consegui remover os itens informados."
                )
            return True

        if not changed and not_found:
            send_text(
                manager.phone_e164,
                "Não achei estes itens na agenda: " + ", ".join(str(x) for x in not_found)
            )
            return True

        header = _build_agenda_bulk_header(
            action=action,
            changed=changed,
            already=already,
            not_found=not_found,
        )

        _clear_agenda_pending_action(checkin, now)
        _send_agenda_snapshot(manager, checkin, header=header)
        _send_agenda_action_menu(manager, checkin)
        return True

    matches = _find_agenda_matches_by_number_or_text(checkin, parsed["text"])

    if action == "done":
        matches = [it for it in matches if it and it.status != "done"]
    elif action == "undo":
        matches = [it for it in matches if it and it.status != "open"]
    elif action == "remove":
        matches = [it for it in matches if it]
    else:
        return False

    if not matches:
        if action == "done":
            send_text(
                manager.phone_e164,
                "Não achei item pendente com esse número ou texto. "
                "Responda com o número, vários números, ou parte do nome."
            )
        elif action == "undo":
            send_text(
                manager.phone_e164,
                "Não achei item concluído/pulado com esse número ou texto. "
                "Responda com o número, vários números, ou parte do nome."
            )
        else:
            send_text(
                manager.phone_e164,
                "Não achei esse item. Responda com o número, vários números, ou parte do nome."
            )
        return True

    if len(matches) > 1:
        preview = "\n".join([f"{it.idx}) {it.text}" for it in matches[:8]])
        if len(matches) > 8:
            preview += "\n..."
        send_text(
            manager.phone_e164,
            "Encontrei mais de um item com esse texto:\n"
            f"{preview}\n\n"
            "Responda com o número correto."
        )
        return True

    it = matches[0]

    if action == "done":
        if it.status == "done":
            logger.warning(
                "AGENDA_PENDING_DUPLICATE_DONE_IGNORED manager=%s checkin_id=%s idx=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                it.idx,
            )
            send_text(manager.phone_e164, "Esse item já está concluído. Me diga outro item.")
            return True

        it.status = "done"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])
        header = f"✅ Item concluído: {it.idx}) {it.text}"

    elif action == "undo":
        if it.status == "open":
            logger.warning(
                "AGENDA_PENDING_DUPLICATE_UNDO_IGNORED manager=%s checkin_id=%s idx=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                it.idx,
            )
            send_text(manager.phone_e164, "Esse item já está em aberto. Me diga outro item.")
            return True

        it.status = "open"
        it.done_at = None
        it.save(update_fields=["status", "done_at"])
        header = f"↩️ Item reaberto: {it.idx}) {it.text}"

    elif action == "remove":
        idx = it.idx
        txt = it.text
        it.delete()
        header = f"🗑️ Item removido: {idx}) {txt}"

    else:
        return False

    _clear_agenda_pending_action(checkin, now)
    _send_agenda_snapshot(manager, checkin, header=header)
    _send_agenda_action_menu(manager, checkin)
    return True


def _agenda_next_idx(checkin):
    from .models import AgendaItem

    last = (
        AgendaItem.objects.filter(checkin=checkin)
        .order_by("-idx")
        .values_list("idx", flat=True)
        .first()
    )
    return int(last or 0) + 1


def _extract_provider_id(resp):
    try:
        if isinstance(resp, dict):
            return ((resp.get("messages") or [{}])[0].get("id") or "").strip()
        return ""
    except Exception:
        return ""


def _response_has_explicit_error(resp):
    """
    Considera erro apenas quando o provider devolve erro explícito.
    Ausência de provider_id não deve abortar o fluxo.
    """
    try:
        if resp is None:
            return False

        if isinstance(resp, dict):
            if resp.get("error"):
                return True

            if resp.get("messages") is not None:
                return False

            return False

        return False
    except Exception:
        return False


def _send_director_summary_text_flow(*, director, managers, day):
    from opscheckin.services.director_agenda_summary import (
        build_director_agenda_summary_blocks,
        build_director_agenda_summary_overview,
    )

    blocks = build_director_agenda_summary_blocks(day=day, managers=managers)
    overview = build_director_agenda_summary_overview(day=day, managers=managers)
    action_body = "Deseja receber as agendas atualizadas?"

    logger.warning(
        "DIRECTOR_TEXT_FLOW_BUILD director=%s phone=%s day=%s managers=%s blocks=%s overview_len=%s director_is_active=%s director_resume_enabled=%s",
        getattr(director, "name", ""),
        getattr(director, "phone_e164", ""),
        day.isoformat(),
        len(managers or []),
        len(blocks or []),
        len(overview or ""),
        getattr(director, "is_active", None),
        getattr(director, "is_active_resume_agenda", None),
    )

    for idx, block in enumerate(blocks or [], start=1):
        try:
            resp_text = send_text(director.phone_e164, block)
        except Exception:
            logger.exception(
                "DIRECTOR_TEXT_FLOW_BLOCK_EXCEPTION director=%s phone=%s day=%s idx=%s",
                getattr(director, "name", ""),
                getattr(director, "phone_e164", ""),
                day.isoformat(),
                idx,
            )
            return False

        _log_outbound_interactive(
            manager=director,
            checkin=None,
            body=block,
            resp=resp_text,
            kind="agenda_summary_director",
        )

        provider_id = _extract_provider_id(resp_text)
        if not provider_id:
            logger.warning(
                "DIRECTOR_TEXT_FLOW_BLOCK_NO_PROVIDER_ID director=%s phone=%s day=%s idx=%s resp=%s",
                getattr(director, "name", ""),
                getattr(director, "phone_e164", ""),
                day.isoformat(),
                idx,
                resp_text,
            )

        if _response_has_explicit_error(resp_text):
            logger.warning(
                "DIRECTOR_TEXT_FLOW_BLOCK_EXPLICIT_ERROR director=%s phone=%s day=%s idx=%s resp=%s",
                getattr(director, "name", ""),
                getattr(director, "phone_e164", ""),
                day.isoformat(),
                idx,
                resp_text,
            )
            return False

    try:
        resp_overview = send_text(director.phone_e164, overview)
    except Exception:
        logger.exception(
            "DIRECTOR_TEXT_FLOW_OVERVIEW_EXCEPTION director=%s phone=%s day=%s",
            getattr(director, "name", ""),
            getattr(director, "phone_e164", ""),
            day.isoformat(),
        )
        return False

    _log_outbound_interactive(
        manager=director,
        checkin=None,
        body=overview,
        resp=resp_overview,
        kind="agenda_summary_director_overview",
    )

    provider_id_overview = _extract_provider_id(resp_overview)
    if not provider_id_overview:
        logger.warning(
            "DIRECTOR_TEXT_FLOW_OVERVIEW_NO_PROVIDER_ID director=%s phone=%s day=%s resp=%s",
            getattr(director, "name", ""),
            getattr(director, "phone_e164", ""),
            day.isoformat(),
            resp_overview,
        )

    if _response_has_explicit_error(resp_overview):
        logger.warning(
            "DIRECTOR_TEXT_FLOW_OVERVIEW_EXPLICIT_ERROR director=%s phone=%s day=%s resp=%s",
            getattr(director, "name", ""),
            getattr(director, "phone_e164", ""),
            day.isoformat(),
            resp_overview,
        )
        return False

    try:
        resp_buttons = send_buttons(
            director.phone_e164,
            body=action_body,
            buttons=[
                {"id": "DIR:REFRESH", "title": "Atualizar agora"},
            ],
        )
    except Exception:
        logger.exception(
            "DIRECTOR_TEXT_FLOW_BUTTON_EXCEPTION director=%s phone=%s day=%s",
            getattr(director, "name", ""),
            getattr(director, "phone_e164", ""),
            day.isoformat(),
        )
        return False

    _log_outbound_interactive(
        manager=director,
        checkin=None,
        body=action_body,
        resp=resp_buttons,
        kind="agenda_summary_director_actions",
    )

    provider_id_buttons = _extract_provider_id(resp_buttons)
    if not provider_id_buttons:
        logger.warning(
            "DIRECTOR_TEXT_FLOW_BUTTON_NO_PROVIDER_ID director=%s phone=%s day=%s resp=%s",
            getattr(director, "name", ""),
            getattr(director, "phone_e164", ""),
            day.isoformat(),
            resp_buttons,
        )

    if _response_has_explicit_error(resp_buttons):
        logger.warning(
            "DIRECTOR_TEXT_FLOW_BUTTON_EXPLICIT_ERROR director=%s phone=%s day=%s resp=%s",
            getattr(director, "name", ""),
            getattr(director, "phone_e164", ""),
            day.isoformat(),
            resp_buttons,
        )
        return False

    logger.warning(
        "DIRECTOR_TEXT_FLOW_SENT director=%s phone=%s day=%s blocks=%s director_is_active=%s director_resume_enabled=%s",
        getattr(director, "name", ""),
        getattr(director, "phone_e164", ""),
        day.isoformat(),
        len(blocks or []),
        getattr(director, "is_active", None),
        getattr(director, "is_active_resume_agenda", None),
    )
    return True


def _handle_director_action(*, manager, reply_id: str, now) -> bool:
    from django.utils import timezone
    from opscheckin.services.recipients import managers_subscribed

    rid = (reply_id or "").strip().upper()
    if rid != "DIR:REFRESH":
        return False

    logger.warning(
        "DIRECTOR_REFRESH_START manager=%s phone=%s reply_id=%s manager_is_active=%s resume_enabled=%s",
        getattr(manager, "name", ""),
        getattr(manager, "phone_e164", ""),
        rid,
        getattr(manager, "is_active", None),
        getattr(manager, "is_active_resume_agenda", None),
    )

    try:
        is_director = bool(getattr(manager, "is_active_resume_agenda", False))

        logger.warning(
            "DIRECTOR_REFRESH_ROLE_CHECK manager=%s is_director=%s manager_is_active=%s resume_enabled=%s",
            getattr(manager, "name", ""),
            is_director,
            getattr(manager, "is_active", None),
            getattr(manager, "is_active_resume_agenda", None),
        )

        if not is_director:
            send_text(
                manager.phone_e164,
                "Você não está habilitado para receber o resumo das agendas."
            )
            logger.warning(
                "DIRECTOR_REFRESH_NOT_ALLOWED manager=%s phone=%s",
                getattr(manager, "name", ""),
                getattr(manager, "phone_e164", ""),
            )
            return True

        day = timezone.localdate()

        managers = list(
            managers_subscribed("agenda_prompt")
            .filter(is_active=True)
            .order_by("name")
        )

        logger.warning(
            "DIRECTOR_REFRESH_MANAGERS_FOUND director=%s total=%s day=%s director_is_active=%s director_resume_enabled=%s",
            getattr(manager, "name", ""),
            len(managers),
            day.isoformat(),
            getattr(manager, "is_active", None),
            getattr(manager, "is_active_resume_agenda", None),
        )

        if not managers:
            send_text(
                manager.phone_e164,
                "Não encontrei managers inscritos para montar o resumo."
            )
            logger.warning(
                "DIRECTOR_REFRESH_NO_MANAGERS director=%s day=%s",
                getattr(manager, "name", ""),
                day.isoformat(),
            )
            return True

        sent_ok = _send_director_summary_text_flow(
            director=manager,
            managers=managers,
            day=day,
        )

        if not sent_ok:
            send_text(manager.phone_e164, "Não consegui atualizar o resumo agora.")
            logger.warning(
                "DIRECTOR_REFRESH_SEND_FAILED director=%s phone=%s day=%s",
                getattr(manager, "name", ""),
                getattr(manager, "phone_e164", ""),
                day.isoformat(),
            )
            return True

        logger.warning(
            "DIRECTOR_REFRESH_COMPLETED director=%s phone=%s day=%s",
            getattr(manager, "name", ""),
            getattr(manager, "phone_e164", ""),
            day.isoformat(),
        )
        return True

    except Exception as e:
        logger.exception(
            "DIRECTOR_REFRESH_EXCEPTION manager=%s phone=%s reply_id=%s err=%s",
            getattr(manager, "name", ""),
            getattr(manager, "phone_e164", ""),
            rid,
            str(e),
        )
        try:
            send_text(manager.phone_e164, "Não consegui atualizar o resumo agora.")
        except Exception:
            logger.exception(
                "DIRECTOR_REFRESH_FALLBACK_SEND_FAILED manager=%s phone=%s",
                getattr(manager, "name", ""),
                getattr(manager, "phone_e164", ""),
            )
        return True


def _handle_agenda_menu_action(*, manager, checkin, reply_id: str, now):
    if reply_id == "AM:MENU:DONE":
        return _send_agenda_pending_action_prompt(manager, checkin, "done", now)

    if reply_id == "AM:MENU:UNDO":
        return _send_agenda_pending_action_prompt(manager, checkin, "undo", now)

    if reply_id == "AM:MENU:REMOVE":
        return _send_agenda_pending_action_prompt(manager, checkin, "remove", now)

    return False


def _handle_agenda_text_command(manager, checkin, text, now):
    """
    Comandos:
      - listar | status
      - feito 2
      - pular 3
      - editar 2: novo texto
      - remover 4
      - + novo item
      - adicionar: novo item
    """
    from .models import AgendaItem

    t = (text or "").strip()

    if _handle_agenda_pending_action_text(manager, checkin, t, now):
        return True

    if CMD_LIST.match(t):
        send_text(manager.phone_e164, _agenda_reply_text(checkin))
        return True

    m = CMD_DONE.match(t)
    if m:
        idx = int(m.group(2))
        it = AgendaItem.objects.filter(checkin=checkin, idx=idx).first()
        if not it:
            send_text(manager.phone_e164, f"Não achei o item {idx}. Envie 'listar' para ver.")
            return True

        if it.status == "done":
            logger.warning(
                "AGENDA_TEXT_DUPLICATE_DONE_IGNORED manager=%s checkin_id=%s idx=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                it.idx,
            )
            return True

        it.status = "done"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])
        _send_agenda_snapshot(manager, checkin, header=f"✅ Item concluído: {it.idx}) {it.text}")
        _send_agenda_action_menu(manager, checkin)
        return True

    m = CMD_SKIP.match(t)
    if m:
        idx = int(m.group(2))
        it = AgendaItem.objects.filter(checkin=checkin, idx=idx).first()
        if not it:
            send_text(manager.phone_e164, f"Não achei o item {idx}. Envie 'listar' para ver.")
            return True
        it.status = "skip"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])
        _send_agenda_snapshot(manager, checkin, header=f"⛔ Item pulado: {it.idx}) {it.text}")
        _send_agenda_action_menu(manager, checkin)
        return True

    m = CMD_REMOVE.match(t)
    if m:
        idx = int(m.group(2))
        it = AgendaItem.objects.filter(checkin=checkin, idx=idx).first()
        if not it:
            send_text(manager.phone_e164, f"Não achei o item {idx}.")
            return True
        txt = it.text
        it.delete()
        _send_agenda_snapshot(manager, checkin, header=f"🗑️ Item removido: {idx}) {txt}")
        _send_agenda_action_menu(manager, checkin)
        return True

    m = CMD_EDIT.match(t)
    if m:
        idx = int(m.group(2))
        new_text = (m.group(3) or "").strip()[:280]
        it = AgendaItem.objects.filter(checkin=checkin, idx=idx).first()
        if not it:
            send_text(manager.phone_e164, f"Não achei o item {idx}.")
            return True
        it.text = new_text
        it.save(update_fields=["text"])
        _send_agenda_snapshot(manager, checkin, header=f"✏️ Item {idx} atualizado")
        _send_agenda_action_menu(manager, checkin)
        return True

    m = CMD_ADD1.match(t) or CMD_ADD2.match(t)
    if m:
        new_text = (m.group(1) if CMD_ADD1.match(t) else m.group(2) or "").strip()[:280]
        if not new_text:
            send_text(manager.phone_e164, "Envie: + texto do item")
            return True
        idx = _agenda_next_idx(checkin)
        AgendaItem.objects.create(checkin=checkin, idx=idx, text=new_text, status="open")
        _send_agenda_snapshot(manager, checkin, header=f"➕ Adicionado como item {idx}")
        _send_agenda_action_menu(manager, checkin)
        return True

    return False


# =========================
# Agenda Items (reply buttons antigos)
# =========================

def _log_outbound_interactive(*, manager, checkin, body, resp, kind="other"):
    now = timezone.now()
    provider_id = ""
    try:
        provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        pass

    data = dict(
        manager=manager,
        checkin=checkin,
        related_question=None,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=body,
        sent_at=now,
        raw_response=resp,
    )
    if provider_id:
        data["wa_status"] = "sent"
        data["wa_sent_at"] = now

    OutboundMessage.objects.create(**data)


def _send_next_agenda_item_prompt(manager, checkin):
    """
    Mantido (botões) como fallback/compat.
    """
    from .models import AgendaItem

    it = (
        AgendaItem.objects.filter(checkin=checkin, status="open")
        .order_by("idx")
        .first()
    )
    if not it:
        return False

    body = f"Item {it.idx}:\n{it.text}\n\nStatus?"
    resp = send_buttons(
        manager.phone_e164,
        body=body,
        buttons=[
            {"id": f"AI:{it.id}:done", "title": "✅ Feito"},
            {"id": f"AI:{it.id}:open", "title": "⏳ Ainda não"},
            {"id": f"AI:{it.id}:skip", "title": "⛔ Pular"},
        ],
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=checkin,
        body=body,
        resp=resp,
        kind="agenda_item",
    )
    return True


def _handle_agenda_item_action(*, manager, checkin, reply_id: str, now):
    """
    reply_id = "AI:<agenda_item_id>:done|open|skip"
    """
    try:
        _, item_id, action = reply_id.split(":", 2)
        item_id = int(item_id)
        action = (action or "").strip()
    except Exception:
        return False

    from .models import AgendaItem

    it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
    if not it:
        return False

    header = ""

    if action == "done":
        if it.status == "done":
            logger.warning(
                "AGENDA_ITEM_DUPLICATE_DONE_IGNORED manager=%s checkin_id=%s item_id=%s idx=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                it.id,
                it.idx,
            )
            return True

        it.status = "done"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])
        header = f"✅ Item concluído: {it.idx}) {it.text}"

    elif action == "skip":
        if it.status != "skip":
            it.status = "skip"
            it.done_at = now
            it.save(update_fields=["status", "done_at"])
            header = f"⛔ Item pulado: {it.idx}) {it.text}"
        else:
            header = f"ℹ️ Esse item já estava pulado: {it.idx}) {it.text}"

    elif action == "open":
        if it.status != "open":
            it.status = "open"
            it.done_at = None
            it.save(update_fields=["status", "done_at"])
            header = f"⏳ Item reaberto: {it.idx}) {it.text}"
        else:
            header = f"ℹ️ Esse item já estava em aberto: {it.idx}) {it.text}"
    else:
        return False

    _send_agenda_snapshot(manager, checkin, header=header)
    _send_agenda_action_menu(manager, checkin)
    return True


# =========================
# NOVO FLUXO: CONFIRMAÇÃO / PROGRESSO (list_reply)
# =========================
# - confirmação: AC:OK | AC:RM:<agenda_item_id> | AC:PAGE:<n> (opcional)
# - progresso:   AP:DONE:<agenda_item_id>

def _get_or_create_confirm_q(checkin, *, now):
    q = checkin.questions.filter(step="AGENDA_CONFIRM").order_by("-id").first()
    if q:
        return q

    return OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA_CONFIRM",
        scheduled_for=now,
        status="pending",
        prompt_text="AGENDA_CONFIRM (auto-created by webhook)",
    )


def _append_confirm_answer(q: OutboundQuestion, line: str):
    cur = (q.answer_text or "").strip()
    q.answer_text = line if not cur else (cur + "\n" + line)


def _handle_confirm_action(*, manager, checkin, reply_id: str, now) -> bool:
    from .models import AgendaItem

    if reply_id == "AC:OK":
        q = checkin.questions.filter(step="AGENDA_CONFIRM").order_by("-id").first()
        if q and q.status == "pending":
            q.status = "answered"
            q.answered_at = now
            q.answer_text = "ok"
            q.save(update_fields=["status", "answered_at", "answer_text"])

        send_text(manager.phone_e164, "Perfeito ✅ Vou acompanhar durante o dia.")
        _send_agenda_action_menu(manager, checkin)
        return True

    if reply_id.startswith("AC:RM:"):
        try:
            item_id = int(reply_id.split(":")[2])
        except Exception:
            return False

        it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
        if not it:
            send_text(manager.phone_e164, "Não achei esse item (talvez já removido).")
            return True

        it.delete()

        items = list(AgendaItem.objects.filter(checkin=checkin).order_by("idx")[:20])
        if not items:
            send_text(manager.phone_e164, "Agenda ficou vazia. Se quiser, envie + texto para adicionar itens.")
            return True

        preview_lines = [f"{x.idx}) {x.text}" for x in items[:12]]
        if len(items) > 12:
            preview_lines.append("…")
        preview = "\n".join(preview_lines)

        body = (
            "Prévia atualizada:\n"
            f"{preview}\n\n"
            "Quer remover mais algum item ou está OK?\n"
            "• Se quiser adicionar: envie + texto"
        )

        sections = [
            {
                "title": "Está OK",
                "rows": [
                    {"id": "AC:OK", "title": "✅ OK (manter agenda)", "description": "Confirmar e seguir"},
                ],
            },
            {
                "title": "Remover outro item",
                "rows": [
                    {
                        "id": f"AC:RM:{x.id}",
                        "title": f"⛔ Remover {x.idx})"[:24],
                        "description": _wa_row_desc(x.text),
                    }
                    for x in items[:9]
                ],
            },
        ]

        sections = _trim_list_sections(sections, max_rows=10)

        resp = send_list(
            manager.phone_e164,
            body=body,
            button_text="Abrir opções",
            sections=sections,
        )

        _log_outbound_interactive(
            manager=manager,
            checkin=checkin,
            body=body,
            resp=resp,
            kind="agenda_confirm_refresh",
        )
        return True

    return False


def _handle_progress_action(*, manager, checkin, reply_id: str, now) -> bool:
    from .models import AgendaItem

    if not reply_id.startswith("AP:DONE:"):
        return False

    try:
        item_id = int(reply_id.split(":")[2])
    except Exception:
        return False

    it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
    if not it:
        try:
            send_text(manager.phone_e164, "Não achei esse item na agenda de hoje.")
        except Exception:
            logger.exception(
                "PROGRESS_ITEM_NOT_FOUND_SEND_FAILED manager=%s checkin_id=%s item_id=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                item_id,
            )
        return True

    if it.status == "done":
        logger.warning(
            "PROGRESS_DUPLICATE_IGNORED manager=%s checkin_id=%s item_id=%s idx=%s",
            getattr(manager, "name", ""),
            getattr(checkin, "id", None),
            it.id,
            it.idx,
        )
        return True

    it.status = "done"
    it.done_at = now
    it.save(update_fields=["status", "done_at"])

    header = f"✅ Item concluído: {it.idx}) {it.text}"
    _send_agenda_snapshot(manager, checkin, header=header)
    _send_agenda_action_menu(manager, checkin)
    return True


# =========================
# Signature
# =========================

def _verify_meta_signature(request) -> bool:
    app_secret = getattr(settings, "META_APP_SECRET", "") or ""
    if not app_secret:
        return True

    sig = request.headers.get("X-Hub-Signature-256", "")
    if not sig.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        msg=request.body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(sig.replace("sha256=", ""), expected)


# =========================
# Status callbacks
# =========================

def _extract_statuses_from_meta(payload: dict):
    out = []
    try:
        entries = payload.get("entry", []) or []
        for entry in entries:
            changes = entry.get("changes", []) or []
            for ch in changes:
                value = ch.get("value") or {}
                statuses = value.get("statuses") or []
                for st in statuses:
                    wamid = (st.get("id") or "").strip()
                    status = (st.get("status") or "").strip()
                    ts = (st.get("timestamp") or "").strip()
                    recipient_id = (st.get("recipient_id") or "").strip()
                    if wamid and status:
                        out.append(
                            {
                                "wamid": wamid,
                                "status": status,
                                "timestamp": ts,
                                "recipient_id": recipient_id,
                                "raw_status": st,
                            }
                        )
    except Exception:
        pass
    return out


def _wa_epoch_to_dt(ts_str: str):
    try:
        return timezone.datetime.fromtimestamp(int(ts_str), tz=timezone.utc)
    except Exception:
        return None


STATUS_ORDER = {"": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 99}


def _apply_status_to_outbound(st: dict) -> bool:
    wamid = (st.get("wamid") or "").strip()
    status = (st.get("status") or "").strip()
    if not wamid or not status:
        return False

    dt = _wa_epoch_to_dt(st.get("timestamp") or "")

    msg = (
        OutboundMessage.objects.select_for_update()
        .filter(provider_message_id=wamid)
        .order_by("-sent_at", "-id")
        .first()
    )
    if not msg:
        return False

    cur = (msg.wa_status or "").strip()
    if STATUS_ORDER.get(status, 0) < STATUS_ORDER.get(cur, 0):
        return True

    msg.wa_status = status
    msg.wa_last_status_payload = st.get("raw_status")

    if status == "sent" and msg.wa_sent_at is None:
        msg.wa_sent_at = dt or timezone.now()
    elif status == "delivered" and msg.wa_delivered_at is None:
        msg.wa_delivered_at = dt or timezone.now()
    elif status == "read" and msg.wa_read_at is None:
        msg.wa_read_at = dt or timezone.now()

    msg.save(
        update_fields=[
            "wa_status",
            "wa_sent_at",
            "wa_delivered_at",
            "wa_read_at",
            "wa_last_status_payload",
        ]
    )
    return True


# =========================
# Inbound extraction
# =========================

def _extract_messages_from_meta(payload: dict):
    out = []
    try:
        entries = payload.get("entry", []) or []
        for entry in entries:
            changes = entry.get("changes", []) or []
            for ch in changes:
                value = ch.get("value") or {}
                messages = value.get("messages") or []
                for msg in messages:
                    from_phone = (msg.get("from") or "").strip()
                    msg_type = (msg.get("type") or "unknown").strip()
                    msg_id = (msg.get("id") or "").strip()

                    reply_id = ""
                    text = ""

                    if msg_type == "text":
                        text = ((msg.get("text") or {}).get("body") or "").strip()

                    elif msg_type == "button":
                        btn = msg.get("button") or {}
                        text = (btn.get("text") or "").strip()
                        reply_id = (btn.get("payload") or "").strip()

                    elif msg_type == "interactive":
                        inter = msg.get("interactive") or {}
                        itype = (inter.get("type") or "").strip()

                        if itype == "button_reply":
                            br = inter.get("button_reply") or {}
                            text = (br.get("title") or "").strip()
                            reply_id = (br.get("id") or "").strip()

                        elif itype == "list_reply":
                            lr = inter.get("list_reply") or {}
                            text = (lr.get("title") or "").strip()
                            reply_id = (lr.get("id") or "").strip()

                    if not text:
                        if msg_type == "audio":
                            text = "🎤 Áudio"
                        elif msg_type == "document":
                            doc = msg.get("document") or {}
                            fn = (doc.get("filename") or "").strip()
                            text = f"📎 Documento: {fn}" if fn else "📎 Documento"
                        elif msg_type == "image":
                            text = "🖼️ Imagem"
                        elif msg_type == "video":
                            text = "🎥 Vídeo"
                        elif msg_type == "sticker":
                            text = "🧩 Sticker"
                        elif msg_type == "location":
                            text = "📍 Localização"
                        else:
                            text = f"({msg_type})"

                    if from_phone:
                        out.append(
                            {
                                "from_phone": from_phone,
                                "text": text,
                                "msg_id": msg_id,
                                "msg_type": msg_type,
                                "reply_id": reply_id,
                                "raw_msg": msg,
                            }
                        )
    except Exception:
        logger.exception("WHATSAPP_EXTRACT_MESSAGES_FAILED")

    return out


# =========================
# Agenda parsing (ignora "Bom dia", trim, etc.)
# =========================

SAUDACOES_RE = re.compile(
    r"^\s*(bom\s+dia|boa\s+tarde|boa\s+noite|ol[áa]|oi|eai|e\s+a[ií]|blz|beleza|tudo\s+bem)\b[!.\-: ]*\s*$",
    re.I,
)


def _parse_agenda_lines(text: str) -> list[str]:
    lines = []
    for raw in (text or "").splitlines():
        s = (raw or "").strip()
        if not s:
            continue

        s = re.sub(r"^\s*(?:[✅⏳⛔]\s*)?(?:[-•*]+|\d{1,2}\s*[.)-]?)\s*", "", s).strip()
        if not s:
            continue

        if SAUDACOES_RE.match(s):
            continue

        if len(s) < 4:
            continue

        lines.append(s[:280])

    seen = set()
    out = []
    for s in lines:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _local_today():
    return timezone.localdate()


# =========================
# Áudio / Transcrição
# =========================

def _get_openai_client():
    api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    return OpenAI(api_key=api_key)


def _get_meta_media_info(media_id: str):
    token = getattr(settings, "WHATSAPP_TOKEN", "") or ""
    version = getattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")

    if not token:
        raise RuntimeError("WHATSAPP_TOKEN não configurado")
    if not media_id:
        raise ValueError("media_id vazio")

    url = f"https://graph.facebook.com/{version}/{media_id}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json() or {}
    return data


def _download_meta_media_to_tempfile(media_url: str, suffix: str = ".ogg"):
    token = getattr(settings, "WHATSAPP_TOKEN", "") or ""
    if not token:
        raise RuntimeError("WHATSAPP_TOKEN não configurado")
    if not media_url:
        raise ValueError("media_url vazia")

    resp = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        stream=True,
    )
    resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                tmp.write(chunk)
        tmp.flush()
        return tmp.name
    finally:
        tmp.close()


def _guess_audio_suffix(mime_type: str) -> str:
    mt = (mime_type or "").lower()
    if "ogg" in mt or "opus" in mt:
        return ".ogg"
    if "mpeg" in mt or "mp3" in mt:
        return ".mp3"
    if "mp4" in mt:
        return ".mp4"
    if "wav" in mt:
        return ".wav"
    if "webm" in mt:
        return ".webm"
    return ".audio"


def _extract_audio_duration_seconds(raw_msg: dict):
    audio = (raw_msg or {}).get("audio") or {}
    media_id = (audio.get("id") or "").strip()
    if not media_id:
        return None

    info = _get_meta_media_info(media_id)
    duration = info.get("file_length") or info.get("duration") or info.get("voice_duration")

    try:
        return int(duration) if duration is not None else None
    except Exception:
        return None


def _transcribe_audio_file(file_path: str) -> str:
    client = _get_openai_client()

    with open(file_path, "rb") as audio_file:
        resp = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file,
        )

    text = getattr(resp, "text", "") or ""
    return text.strip()


def _transcribe_whatsapp_audio_from_message(raw_msg: dict) -> str:
    audio = (raw_msg or {}).get("audio") or {}
    media_id = (audio.get("id") or "").strip()
    mime_type = (audio.get("mime_type") or "").strip()

    if not media_id:
        return ""

    media_info = _get_meta_media_info(media_id)
    media_url = (media_info.get("url") or "").strip()
    if not media_url:
        return ""

    suffix = _guess_audio_suffix(mime_type)

    temp_path = None
    try:
        temp_path = _download_meta_media_to_tempfile(media_url, suffix=suffix)
        if not temp_path:
            return ""

        text = _transcribe_audio_file(temp_path)
        return (text or "").strip()

    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                logger.exception("WHATSAPP_AUDIO_TEMPFILE_DELETE_FAILED path=%s", temp_path)


# =========================
# Webhook
# =========================

@csrf_exempt
def whatsapp_webhook(request):
    try:
        try:
            raw = request.body.decode("utf-8", errors="replace") if request.body else ""
        except Exception:
            raw = ""

        logger.warning(
            "WHATSAPP_WEBHOOK hit method=%s path=%s query=%s content_type=%s len=%s xhub=%s",
            request.method,
            request.path,
            request.META.get("QUERY_STRING", ""),
            request.META.get("CONTENT_TYPE", ""),
            len(request.body or b""),
            (request.headers.get("X-Hub-Signature-256", "") or "")[:32],
        )
        if raw:
            logger.warning("WHATSAPP_WEBHOOK body=%s", raw[:4000])

        if request.method == "GET":
            mode = request.GET.get("hub.mode")
            token = request.GET.get("hub.verify_token")
            challenge = request.GET.get("hub.challenge")

            verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
            if mode == "subscribe" and token and token == verify_token and challenge:
                return HttpResponse(challenge, status=200)
            return HttpResponse("forbidden", status=403)

        if request.method != "POST":
            return JsonResponse({"ok": True})

        if not _verify_meta_signature(request):
            return HttpResponse("invalid signature", status=403)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            logger.exception("WHATSAPP_WEBHOOK_INVALID_JSON")
            return JsonResponse({"ok": True})

        statuses = _extract_statuses_from_meta(payload)
        if statuses:
            try:
                with transaction.atomic():
                    applied = 0
                    for st in statuses:
                        if _apply_status_to_outbound(st):
                            applied += 1
                logger.warning(
                    "WHATSAPP_WEBHOOK statuses_received=%s statuses_applied=%s",
                    len(statuses),
                    applied,
                )
            except Exception:
                logger.exception("WHATSAPP_WEBHOOK failed to apply statuses")

        msgs = _extract_messages_from_meta(payload)
        if not msgs:
            return JsonResponse({"ok": True})

        today = _local_today()
        now = timezone.now()

        for msg in msgs:
            inbound = None
            try:
                from_phone = msg["from_phone"]
                text = msg["text"]
                msg_id = (msg.get("msg_id") or "").strip()
                msg_type = (msg.get("msg_type") or "text").strip() or "text"
                reply_id = (msg.get("reply_id") or "").strip()

                manager = Manager.objects.filter(phone_e164=from_phone).first()

                is_checkin_user = bool(manager and manager.is_active)
                is_resume_director = bool(manager and manager.is_active_resume_agenda)

                checkin = None
                if is_checkin_user:
                    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=today)

                logger.warning(
                    "WHATSAPP_WEBHOOK_MANAGER_RESOLUTION manager=%s phone=%s is_active=%s is_resume_director=%s has_checkin=%s reply_id=%s",
                    getattr(manager, "name", "") if manager else "",
                    from_phone,
                    getattr(manager, "is_active", None) if manager else None,
                    getattr(manager, "is_active_resume_agenda", None) if manager else None,
                    bool(checkin),
                    reply_id,
                )

                inbound_defaults = dict(
                    manager=manager,
                    from_phone=from_phone,
                    text=text,
                    msg_type=msg_type,
                    received_at=now,
                    checkin=checkin,
                    linked_question=None,
                    raw_payload=msg.get("raw_msg"),
                    processed=False,
                )

                if msg_id:
                    inbound, created = InboundMessage.objects.get_or_create(
                        wa_message_id=msg_id,
                        defaults=inbound_defaults,
                    )
                    if not created:
                        logger.warning(
                            "WHATSAPP_WEBHOOK_DUPLICATE msg_id=%s from=%s reply_id=%s",
                            msg_id, from_phone, reply_id
                        )
                        continue
                else:
                    inbound = InboundMessage.objects.create(
                        wa_message_id="",
                        **inbound_defaults,
                    )

                if not manager:
                    logger.warning(
                        "WHATSAPP_WEBHOOK_MANAGER_NOT_FOUND from_phone=%s reply_id=%s",
                        from_phone,
                        reply_id,
                    )
                    _mark_inbound_processed(inbound, now)
                    continue

                if msg_type == "audio":
                    logger.warning(
                        "WHATSAPP_AUDIO_RECEIVED manager=%s phone=%s msg_id=%s",
                        getattr(manager, "name", ""),
                        from_phone,
                        msg_id,
                    )

                    try:
                        duration_seconds = _extract_audio_duration_seconds(
                            msg.get("raw_msg") or {}
                        )
                    except Exception:
                        logger.exception(
                            "WHATSAPP_AUDIO_DURATION_CHECK_FAILED manager=%s phone=%s msg_id=%s",
                            getattr(manager, "name", ""),
                            from_phone,
                            msg_id,
                        )
                        duration_seconds = None

                    if duration_seconds is not None and duration_seconds > MAX_AUDIO_SECONDS:
                        logger.warning(
                            "WHATSAPP_AUDIO_TOO_LONG manager=%s phone=%s msg_id=%s duration_seconds=%s",
                            getattr(manager, "name", ""),
                            from_phone,
                            msg_id,
                            duration_seconds,
                        )
                        try:
                            send_text(
                                manager.phone_e164,
                                "Recebi seu áudio, mas no momento só consigo processar áudios de até 5 minutos. Pode me enviar um áudio menor ou por escrito?"
                            )
                        except Exception:
                            logger.exception(
                                "WHATSAPP_AUDIO_TOO_LONG_REPLY_FAILED manager=%s phone=%s msg_id=%s",
                                getattr(manager, "name", ""),
                                from_phone,
                                msg_id,
                            )

                        _mark_inbound_processed(inbound, now)
                        continue

                    try:
                        transcribed_text = _transcribe_whatsapp_audio_from_message(
                            msg.get("raw_msg") or {}
                        )
                    except Exception:
                        logger.exception(
                            "WHATSAPP_AUDIO_TRANSCRIPTION_FAILED manager=%s phone=%s msg_id=%s",
                            getattr(manager, "name", ""),
                            from_phone,
                            msg_id,
                        )
                        try:
                            send_text(
                                manager.phone_e164,
                                "Recebi seu áudio, mas não consegui processá-lo agora. Pode me enviar por escrito?"
                            )
                        except Exception:
                            logger.exception(
                                "WHATSAPP_AUDIO_TRANSCRIPTION_FAILED_REPLY_FAILED manager=%s phone=%s msg_id=%s",
                                getattr(manager, "name", ""),
                                from_phone,
                                msg_id,
                            )

                        _mark_inbound_processed(inbound, now)
                        continue

                    if not transcribed_text:
                        logger.warning(
                            "WHATSAPP_AUDIO_TRANSCRIPTION_EMPTY manager=%s phone=%s msg_id=%s",
                            getattr(manager, "name", ""),
                            from_phone,
                            msg_id,
                        )
                        try:
                            send_text(
                                manager.phone_e164,
                                "Recebi seu áudio, mas não consegui entender o conteúdo. Pode me enviar por escrito?"
                            )
                        except Exception:
                            logger.exception(
                                "WHATSAPP_AUDIO_TRANSCRIPTION_EMPTY_REPLY_FAILED manager=%s phone=%s msg_id=%s",
                                getattr(manager, "name", ""),
                                from_phone,
                                msg_id,
                            )

                        _mark_inbound_processed(inbound, now)
                        continue

                    logger.warning(
                        "WHATSAPP_AUDIO_TRANSCRIBED manager=%s phone=%s msg_id=%s text=%r",
                        getattr(manager, "name", ""),
                        from_phone,
                        msg_id,
                        transcribed_text[:500],
                    )

                    text = transcribed_text
                    msg_type = "text"

                    try:
                        inbound.text = transcribed_text
                        inbound.raw_payload = {
                            **(inbound.raw_payload or {}),
                            "_audio_transcription": transcribed_text,
                        }
                        inbound.save(update_fields=["text", "raw_payload"])
                    except Exception:
                        logger.exception(
                            "WHATSAPP_AUDIO_TRANSCRIPTION_SAVE_FAILED manager=%s phone=%s msg_id=%s",
                            getattr(manager, "name", ""),
                            from_phone,
                            msg_id,
                        )

                # ==========
                # 1) actions via reply_id (ordem importa)
                # ==========

                if reply_id.startswith("DIR:"):
                    logger.warning(
                        "WEBHOOK_DIR_ACTION manager=%s phone=%s reply_id=%s resume_enabled=%s",
                        getattr(manager, "name", ""),
                        getattr(manager, "phone_e164", ""),
                        reply_id,
                        is_resume_director,
                    )
                    if _handle_director_action(manager=manager, reply_id=reply_id, now=now):
                        _mark_inbound_processed(inbound, now)
                        continue

                # Daqui em diante exige participação no check-in diário
                if not is_checkin_user or not checkin:
                    logger.warning(
                        "WHATSAPP_WEBHOOK_MANAGER_NOT_ELIGIBLE_FOR_CHECKIN manager=%s phone=%s is_active=%s has_checkin=%s reply_id=%s",
                        getattr(manager, "name", ""),
                        from_phone,
                        getattr(manager, "is_active", None),
                        bool(checkin),
                        reply_id,
                    )
                    _mark_inbound_processed(inbound, now)
                    continue

                if reply_id.startswith("AM:"):
                    if _handle_agenda_menu_action(
                        manager=manager,
                        checkin=checkin,
                        reply_id=reply_id,
                        now=now,
                    ):
                        _mark_inbound_processed(inbound, now)
                        continue

                if reply_id.startswith("AI:"):
                    if _handle_agenda_item_action(
                        manager=manager, checkin=checkin, reply_id=reply_id, now=now
                    ):
                        _mark_inbound_processed(inbound, now)
                        continue

                if reply_id.startswith("AC:"):
                    if _handle_confirm_action(
                        manager=manager, checkin=checkin, reply_id=reply_id, now=now
                    ):
                        _mark_inbound_processed(inbound, now)
                        continue

                if reply_id.startswith("AP:"):
                    if _handle_progress_action(
                        manager=manager, checkin=checkin, reply_id=reply_id, now=now
                    ):
                        _mark_inbound_processed(inbound, now)
                        continue

                # ==========
                # 2) comandos por texto
                # ==========
                if msg_type == "text":
                    if _handle_agenda_text_command(manager, checkin, text, now):
                        _mark_inbound_processed(inbound, now)
                        continue

                # ==========
                # 3) link com pergunta pendente
                # ==========
                pending = (
                    OutboundQuestion.objects.filter(
                        checkin=checkin,
                        status="pending",
                        answered_at__isnull=True,
                        sent_at__isnull=False,
                    )
                    .order_by("sent_at", "scheduled_for", "id")
                    .first()
                )
                if not pending:
                    _mark_inbound_processed(inbound, now)
                    continue

                prev = (pending.answer_text or "").strip()
                cur = (text or "").strip()
                pending.answer_text = cur if not prev else (prev + "\n" + cur)

                became_answered = False
                combined = (pending.answer_text or "").strip()
                parsed_items = _parse_agenda_lines(combined)

                if pending.step == "AGENDA":
                    if parsed_items and len(combined) >= MIN_AGENDA_CHARS:
                        pending.answered_at = now
                        pending.status = "answered"
                        became_answered = True
                        pending.save(update_fields=["answered_at", "answer_text", "status"])
                    else:
                        pending.save(update_fields=["answer_text"])
                else:
                    if len(combined) >= MIN_AGENDA_CHARS:
                        pending.answered_at = now
                        pending.status = "answered"
                        became_answered = True
                        pending.save(update_fields=["answered_at", "answer_text", "status"])
                    else:
                        pending.save(update_fields=["answer_text"])

                if became_answered and pending.step == "AGENDA":
                    from .models import AgendaItem

                    if parsed_items:
                        if not AgendaItem.objects.filter(checkin=checkin).exists():
                            bulk = [
                                AgendaItem(checkin=checkin, idx=i, text=t, status="open")
                                for i, t in enumerate(parsed_items, start=1)
                            ]
                            AgendaItem.objects.bulk_create(bulk)

                        logger.warning(
                            "AGENDA_PARSED_ITEMS count=%s manager=%s checkin_id=%s",
                            len(parsed_items), manager.name, checkin.id
                        )

                _mark_inbound_processed(inbound, now, linked_question=pending)

            except Exception:
                logger.exception(
                    "WHATSAPP_WEBHOOK_MSG_FAILED from=%s msg_id=%s reply_id=%s",
                    msg.get("from_phone"),
                    msg.get("msg_id"),
                    msg.get("reply_id"),
                )
                try:
                    if inbound and not inbound.processed:
                        _mark_inbound_processed(inbound, now)
                except Exception:
                    logger.exception("WHATSAPP_WEBHOOK_MSG_FAILED_MARK_PROCESSED")
                continue

        return JsonResponse({"ok": True})

    except Exception:
        logger.exception("WHATSAPP_WEBHOOK_FATAL")
        return JsonResponse({"ok": True})