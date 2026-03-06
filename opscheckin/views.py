# opscheckin/views.py
import re
import json
import hmac
import hashlib
import logging

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


# =========================
# COMANDOS POR TEXTO
# =========================

CMD_DONE = re.compile(r"^(feito|done)\s+(\d{1,3})\s*$", re.I)
CMD_SKIP = re.compile(r"^(pular|skip)\s+(\d{1,3})\s*$", re.I)
CMD_REMOVE = re.compile(r"^(remover|delete)\s+(\d{1,3})\s*$", re.I)
CMD_EDIT = re.compile(r"^(editar|edit)\s+(\d{1,3})\s*[:\-]\s*(.+)$", re.I)
CMD_ADD1 = re.compile(r"^\+\s*(.+)$", re.I)
CMD_ADD2 = re.compile(r"^(adicionar|add)\s*[:\-]\s*(.+)$", re.I)
CMD_LIST = re.compile(r"^(listar|status|lista)\s*$", re.I)


def _mark_inbound_processed(inbound, now, *, linked_question=None):
    fields = ["processed", "processed_at"]
    inbound.processed = True
    inbound.processed_at = now

    if linked_question is not None:
        inbound.linked_question = linked_question
        fields.append("linked_question")

    inbound.save(update_fields=fields)


def _wa_row_title(idx: int, text: str, prefix: str = "") -> str:
    raw = f"{prefix}{idx}) {(text or '').strip()}".strip()
    return raw[:24].rstrip()


def _wa_row_desc(text: str) -> str:
    s = (text or "").strip()
    return (s[:72] + "…") if len(s) > 72 else s


def _handle_director_action(*, manager, reply_id: str, now) -> bool:
    from django.utils import timezone
    from opscheckin.services.recipients import managers_subscribed
    from opscheckin.services.director_agenda_summary import build_director_agenda_summary

    rid = (reply_id or "").strip().upper()
    if rid != "DIR:REFRESH":
        return False

    is_director = manager.notification_subscriptions.filter(
        notification_type__code="agenda_summary_director",
        notification_type__is_active=True,
        is_active=True,
    ).exists()

    if not is_director:
        send_text(manager.phone_e164, "Você não está habilitado para receber o resumo das agendas.")
        return True

    day = timezone.localdate()
    managers = list(managers_subscribed("agenda_prompt").order_by("name"))

    if not managers:
        send_text(manager.phone_e164, "Não encontrei managers inscritos para montar o resumo.")
        return True

    body = build_director_agenda_summary(day=day, managers=managers)

    resp = send_buttons(
        manager.phone_e164,
        body=body,
        buttons=[
            {"id": "DIR:REFRESH", "title": "🔄 Atualizar agendas"},
        ],
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=None,
        body=body,
        resp=resp,
        kind="agenda_summary_director",
    )

    return True


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
    body = "O que você quer fazer agora na agenda?"

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


def _send_agenda_done_picker(manager, checkin):
    from .models import AgendaItem

    items = list(
        AgendaItem.objects.filter(checkin=checkin, status="open")
        .order_by("idx")[:10]
    )

    if not items:
        send_text(manager.phone_e164, "Não há itens pendentes para concluir.")
        _send_agenda_action_menu(manager, checkin)
        return True

    sections = [{
        "title": "Itens pendentes",
        "rows": [
            {
                "id": f"AM:DONE:{it.id}",
                "title": _wa_row_title(it.idx, it.text),
                "description": _wa_row_desc(it.text),
            }
            for it in items
        ],
    }]

    body = "Selecione o item concluído:"
    resp = send_list(
        manager.phone_e164,
        body=body,
        button_text="Selecionar",
        sections=sections,
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=checkin,
        body=body,
        resp=resp,
        kind="agenda_done_picker",
    )

    return True


def _send_agenda_undo_picker(manager, checkin):
    from .models import AgendaItem

    items = list(
        AgendaItem.objects.filter(checkin=checkin, status="done")
        .order_by("idx")[:10]
    )

    if not items:
        send_text(manager.phone_e164, "Nenhum item concluído para desmarcar.")
        _send_agenda_action_menu(manager, checkin)
        return True

    sections = [{
        "title": "Itens concluídos",
        "rows": [
            {
                "id": f"AM:UNDO:{it.id}",
                "title": _wa_row_title(it.idx, it.text),
                "description": _wa_row_desc(it.text),
            }
            for it in items
        ],
    }]

    body = "Selecione o item para reabrir:"
    resp = send_list(
        manager.phone_e164,
        body=body,
        button_text="Selecionar",
        sections=sections,
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=checkin,
        body=body,
        resp=resp,
        kind="agenda_undo_picker",
    )

    return True


def _send_agenda_remove_picker(manager, checkin):
    from .models import AgendaItem

    items = list(
        AgendaItem.objects.filter(checkin=checkin)
        .order_by("idx")[:10]
    )

    if not items:
        send_text(manager.phone_e164, "Agenda vazia.")
        return True

    sections = [{
        "title": "Remover item",
        "rows": [
            {
                "id": f"AM:REMOVE:{it.id}",
                "title": _wa_row_title(it.idx, it.text),
                "description": _wa_row_desc(it.text),
            }
            for it in items
        ],
    }]

    body = "Selecione o item para remover:"
    resp = send_list(
        manager.phone_e164,
        body=body,
        button_text="Selecionar",
        sections=sections,
    )

    _log_outbound_interactive(
        manager=manager,
        checkin=checkin,
        body=body,
        resp=resp,
        kind="agenda_remove_picker",
    )

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


def _handle_agenda_menu_action(*, manager, checkin, reply_id: str, now):
    from .models import AgendaItem

    if reply_id == "AM:MENU:DONE":
        return _send_agenda_done_picker(manager, checkin)

    if reply_id == "AM:MENU:UNDO":
        return _send_agenda_undo_picker(manager, checkin)

    if reply_id == "AM:MENU:REMOVE":
        return _send_agenda_remove_picker(manager, checkin)

    if reply_id.startswith("AM:DONE:"):
        try:
            item_id = int(reply_id.split(":")[2])
        except Exception:
            return False

        it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
        if not it:
            send_text(manager.phone_e164, "Não achei esse item.")
            return True

        if it.status == "done":
            logger.warning(
                "AGENDA_MENU_DUPLICATE_DONE_IGNORED manager=%s checkin_id=%s item_id=%s idx=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                it.id,
                it.idx,
            )
            return True

        it.status = "done"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])

        _send_agenda_snapshot(manager, checkin, header=f"✅ Item concluído: {it.idx}) {it.text}")
        _send_agenda_action_menu(manager, checkin)
        return True

    if reply_id.startswith("AM:UNDO:"):
        try:
            item_id = int(reply_id.split(":")[2])
        except Exception:
            return False

        it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
        if not it:
            send_text(manager.phone_e164, "Não achei esse item.")
            return True

        if it.status == "open":
            logger.warning(
                "AGENDA_MENU_DUPLICATE_UNDO_IGNORED manager=%s checkin_id=%s item_id=%s idx=%s",
                getattr(manager, "name", ""),
                getattr(checkin, "id", None),
                it.id,
                it.idx,
            )
            return True

        it.status = "open"
        it.done_at = None
        it.save(update_fields=["status", "done_at"])

        _send_agenda_snapshot(manager, checkin, header=f"↩️ Item reaberto: {it.idx}) {it.text}")
        _send_agenda_action_menu(manager, checkin)
        return True

    if reply_id.startswith("AM:REMOVE:"):
        try:
            item_id = int(reply_id.split(":")[2])
        except Exception:
            return False

        it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
        if not it:
            send_text(manager.phone_e164, "Não achei esse item.")
            return True

        txt = it.text
        idx = it.idx
        it.delete()

        _send_agenda_snapshot(manager, checkin, header=f"🗑️ Item removido: {idx}) {txt}")
        _send_agenda_action_menu(manager, checkin)
        return True

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

        removed_label = f"{it.idx}) {it.text[:80]}"
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
                    for x in items[:10]
                ],
            },
        ]

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
                        text = (msg.get("button", {}).get("text") or "").strip()
                    elif msg_type == "interactive":
                        inter = msg.get("interactive") or {}
                        itype = inter.get("type")
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
        pass

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

        s = re.sub(r"^\s*(?:[-•*]+|\d{1,2}\s*[.)-]?)\s*", "", s).strip()
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

                manager = Manager.objects.filter(phone_e164=from_phone, is_active=True).first()
                checkin = None
                if manager:
                    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=today)

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

                if not manager or not checkin:
                    _mark_inbound_processed(inbound, now)
                    continue

                # ==========
                # 1) actions via reply_id (ordem importa)
                # ==========

                if reply_id.startswith("DIR:"):
                    if _handle_director_action(manager=manager, reply_id=reply_id, now=now):
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