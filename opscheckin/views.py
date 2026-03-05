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

from opscheckin.services.whatsapp import send_buttons, send_text

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


def _agenda_reply_text(checkin):
    from .models import AgendaItem

    items = AgendaItem.objects.filter(checkin=checkin).order_by("idx")
    if not items.exists():
        return "Ainda não tenho itens de agenda para hoje."

    lines = []
    for it in items:
        mark = "✅" if it.status == "done" else ("⛔" if it.status == "skip" else "☐")
        lines.append(f"{mark} {it.idx}) {it.text}")

    return "Agenda de hoje:\n" + "\n".join(lines)


def _agenda_next_idx(checkin):
    from .models import AgendaItem

    last = (
        AgendaItem.objects.filter(checkin=checkin)
        .order_by("-idx")
        .values_list("idx", flat=True)
        .first()
    )
    return int(last or 0) + 1


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
        it.status = "done"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])
        _send_next_agenda_item_prompt(manager, checkin)
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
        _send_next_agenda_item_prompt(manager, checkin)
        return True

    m = CMD_REMOVE.match(t)
    if m:
        idx = int(m.group(2))
        it = AgendaItem.objects.filter(checkin=checkin, idx=idx).first()
        if not it:
            send_text(manager.phone_e164, f"Não achei o item {idx}.")
            return True
        it.delete()
        send_text(manager.phone_e164, f"Item {idx} removido. Envie 'listar' para ver a agenda.")
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
        send_text(manager.phone_e164, f"Item {idx} atualizado ✅")
        return True

    m = CMD_ADD1.match(t) or CMD_ADD2.match(t)
    if m:
        new_text = (m.group(1) if CMD_ADD1.match(t) else m.group(2) or "").strip()[:280]
        if not new_text:
            send_text(manager.phone_e164, "Envie: + texto do item")
            return True
        idx = _agenda_next_idx(checkin)
        AgendaItem.objects.create(checkin=checkin, idx=idx, text=new_text, status="open")
        send_text(manager.phone_e164, f"Adicionado como item {idx} ✅")
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

    if action == "done":
        if it.status != "done":
            it.status = "done"
            it.done_at = now
            it.save(update_fields=["status", "done_at"])
    elif action == "skip":
        if it.status != "skip":
            it.status = "skip"
            it.done_at = now
            it.save(update_fields=["status", "done_at"])
    elif action == "open":
        if it.status != "open":
            it.status = "open"
            it.done_at = None
            it.save(update_fields=["status", "done_at"])

    _send_next_agenda_item_prompt(manager, checkin)
    return True


# =========================
# NOVO FLUXO: CONFIRMAÇÃO / PROGRESSO (list_reply)
# =========================
# - confirmação: AC:OK | AC:RM:<agenda_item_id> | AC:PAGE:<n> (opcional)
# - progresso:   AP:DONE:<agenda_item_id>

def _get_or_create_confirm_q(checkin, *, now):
    """
    Segurança: se por qualquer motivo não existir AGENDA_CONFIRM,
    cria e mantém auditoria.
    """
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
    from opscheckin.services.whatsapp import send_text, send_list

    if reply_id == "AC:OK":
        q = checkin.questions.filter(step="AGENDA_CONFIRM").order_by("-id").first()
        if q and q.status == "pending":
            q.status = "answered"
            q.answered_at = now
            q.answer_text = "ok"
            q.save(update_fields=["status", "answered_at", "answer_text"])

        send_text(manager.phone_e164, "Perfeito ✅ Vou acompanhar durante o dia.")
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

        # 1) confirma remoção
        send_text(manager.phone_e164, f"Item removido ✅ ({removed_label})")

        # 2) reenviar lista atualizada (mesma confirmação)
        items = list(AgendaItem.objects.filter(checkin=checkin).order_by("idx")[:20])
        if not items:
            send_text(manager.phone_e164, "Agenda ficou vazia. Se quiser, envie + texto para adicionar itens.")
            return True

        # preview curtinha
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
                        "title": f"⛔ Remover {x.idx})",
                        "description": (x.text[:60] + "…") if len(x.text) > 60 else x.text,
                    }
                    for x in items
                ],
            },
        ]

        send_list(
            manager.phone_e164,
            body=body,
            button_text="Abrir opções",
            sections=sections,
        )
        return True

    return False


def _handle_progress_action(*, manager, checkin, reply_id: str, now) -> bool:
    from .models import AgendaItem
    from opscheckin.services.whatsapp import send_text, send_list

    if not reply_id.startswith("AP:DONE:"):
        return False
    try:
        item_id = int(reply_id.split(":")[2])
    except Exception:
        return False

    it = AgendaItem.objects.filter(id=item_id, checkin=checkin).first()
    if not it:
        return False

    if it.status != "done":
        it.status = "done"
        it.done_at = now
        it.save(update_fields=["status", "done_at"])

    # ✅ feedback imediato
    send_text(manager.phone_e164, f"✅ Fechado: {it.idx}) {it.text[:80]}")

    # ✅ se ainda houver itens open, manda outra lista pra marcar outro
    open_items = list(AgendaItem.objects.filter(checkin=checkin, status="open").order_by("idx")[:10])
    if open_items:
        body = "Quer marcar mais algum como concluído?"
        sections = [{
            "title": "Marcar como concluído",
            "rows": [
                {
                    "id": f"AP:DONE:{x.id}",
                    "title": f"✅ {x.idx}) {x.text[:60]}",
                    "description": (x.text[:60] + "…") if len(x.text) > 60 else x.text,
                }
                for x in open_items
            ],
        }]
        send_list(
            manager.phone_e164,
            body=body,
            button_text="Selecionar item",
            sections=sections,
        )
    else:
        send_text(manager.phone_e164, "🎉 Agenda do dia finalizada! Se precisar, envie + para adicionar item.")

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

        # remove bullets / numeração
        s = re.sub(r"^\s*(?:[-•*]+|\d{1,2}\s*[.)-]?)\s*", "", s).strip()
        if not s:
            continue

        if SAUDACOES_RE.match(s):
            continue

        if len(s) < 4:
            continue

        lines.append(s[:280])

    # dedupe preservando ordem
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

    # GET verify
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
        return JsonResponse({"ok": True})

    # 1) status callbacks
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

    # 2) inbound messages
    msgs = _extract_messages_from_meta(payload)
    if not msgs:
        return JsonResponse({"ok": True})

    today = _local_today()
    now = timezone.now()

    for msg in msgs:
        from_phone = msg["from_phone"]
        text = msg["text"]
        msg_id = (msg.get("msg_id") or "").strip()
        msg_type = (msg.get("msg_type") or "text").strip() or "text"
        reply_id = (msg.get("reply_id") or "").strip()

        # dedupe por msg_id
        if msg_id and InboundMessage.objects.filter(wa_message_id=msg_id).exists():
            continue

        manager = Manager.objects.filter(phone_e164=from_phone, is_active=True).first()

        checkin = None
        if manager:
            checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=today)

        inbound = InboundMessage.objects.create(
            manager=manager,
            from_phone=from_phone,
            wa_message_id=msg_id,
            text=text,
            msg_type=msg_type,
            received_at=now,
            checkin=checkin,
            linked_question=None,
            raw_payload=msg.get("raw_msg"),
            processed=False,
        )

        # sem manager/checkin: só registra inbound
        if not manager or not checkin:
            continue

        # ==========
        # 1) actions via reply_id (ordem importa)
        # ==========

        if reply_id.startswith("AI:"):
            _handle_agenda_item_action(manager=manager, checkin=checkin, reply_id=reply_id, now=now)
            inbound.processed = True
            inbound.processed_at = now
            inbound.save(update_fields=["processed", "processed_at"])
            continue

        if reply_id.startswith("AC:"):
            if _handle_confirm_action(manager=manager, checkin=checkin, reply_id=reply_id, now=now):
                inbound.processed = True
                inbound.processed_at = now
                inbound.save(update_fields=["processed", "processed_at"])
                continue

        if reply_id.startswith("AP:"):
            if _handle_progress_action(manager=manager, checkin=checkin, reply_id=reply_id, now=now):
                inbound.processed = True
                inbound.processed_at = now
                inbound.save(update_fields=["processed", "processed_at"])
                continue

        # ==========
        # 2) comandos por texto
        # ==========
        if msg_type == "text":
            if _handle_agenda_text_command(manager, checkin, text, now):
                inbound.processed = True
                inbound.processed_at = now
                inbound.save(update_fields=["processed", "processed_at"])
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
            continue

        prev = (pending.answer_text or "").strip()
        cur = (text or "").strip()
        pending.answer_text = cur if not prev else (prev + "\n" + cur)

        became_answered = False

        # ✅ critério real: parse gerar pelo menos 1 item
        # (anti-“Bom dia”, anti-vazio, etc.)
        combined = (pending.answer_text or "").strip()
        parsed_items = _parse_agenda_lines(combined)

        if pending.step == "AGENDA":
            # “anti-ruído”: também exige um mínimo de caracteres no total,
            # pra não disparar por mensagens curtíssimas (mas o parse manda).
            if parsed_items and len(combined) >= MIN_AGENDA_CHARS:
                pending.answered_at = now
                pending.status = "answered"
                became_answered = True
                pending.save(update_fields=["answered_at", "answer_text", "status"])
            else:
                pending.save(update_fields=["answer_text"])
        else:
            # outros steps: mantém comportamento simples por texto
            if len(combined) >= MIN_AGENDA_CHARS:
                pending.answered_at = now
                pending.status = "answered"
                became_answered = True
                pending.save(update_fields=["answered_at", "answer_text", "status"])
            else:
                pending.save(update_fields=["answer_text"])

        # ==========
        # 4) se AGENDA virou answered -> cria itens (uma vez)
        #    confirmação 10min depois: agenda_confirm_tick
        # ==========
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

        inbound.linked_question = pending
        inbound.processed = True
        inbound.processed_at = now
        inbound.save(update_fields=["linked_question", "processed", "processed_at"])

    return JsonResponse({"ok": True})