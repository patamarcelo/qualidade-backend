# opscheckin/views.py
import json
import hmac
import hashlib

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import Manager, DailyCheckin, OutboundQuestion

import logging

logger = logging.getLogger("opscheckin.whatsapp")

def _verify_meta_signature(request) -> bool:
    """
    Validação opcional (RECOMENDADA em produção):
    confere X-Hub-Signature-256 com o APP_SECRET.
    """
    app_secret = getattr(settings, "META_APP_SECRET", "") or ""
    if not app_secret:
        return True  # se não configurou, não bloqueia (MVP)

    sig = request.headers.get("X-Hub-Signature-256", "")
    if not sig.startswith("sha256="):
        return False

    expected = hmac.new(
        app_secret.encode("utf-8"),
        msg=request.body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(sig.replace("sha256=", ""), expected)


def _extract_messages_from_meta(payload: dict):
    """
    Extrai (from_phone, text) do payload real do WhatsApp Cloud API.
    Retorna lista de tuplas.
    """
    out = []
    try:
        entries = payload.get("entry", []) or []
        for entry in entries:
            changes = entry.get("changes", []) or []
            for ch in changes:
                value = (ch.get("value") or {})
                messages = value.get("messages") or []
                for msg in messages:
                    from_phone = (msg.get("from") or "").strip()  # ex: "5511999999999"
                    mtype = msg.get("type")

                    text = ""
                    if mtype == "text":
                        text = ((msg.get("text") or {}).get("body") or "").strip()
                    elif mtype == "button":
                        # se usar botões interativos
                        text = (msg.get("button", {}).get("text") or "").strip()
                    elif mtype == "interactive":
                        inter = msg.get("interactive") or {}
                        itype = inter.get("type")
                        if itype == "button_reply":
                            text = (inter.get("button_reply", {}).get("title") or "").strip()
                        elif itype == "list_reply":
                            text = (inter.get("list_reply", {}).get("title") or "").strip()

                    if from_phone and text:
                        out.append((from_phone, text))
    except Exception:
        pass
    return out


@csrf_exempt
def whatsapp_webhook(request):
    # 1) Verificação do webhook (Meta faz GET com hub.challenge)
    print('chegou a requisição da META:')# DEBUG: log básico de toda chamada
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
        request.headers.get("X-Hub-Signature-256", "")[:32],  # só prefixo
    )

    if raw:
        # cuidado com tamanho: limita pra não poluir log
        logger.warning("WHATSAPP_WEBHOOK body=%s", raw[:4000])
        
    
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        if mode == "subscribe" and token and token == verify_token and challenge:
            return HttpResponse(challenge, status=200)

        return HttpResponse("forbidden", status=403)

    # 2) Recebimento de mensagens (POST)
    if request.method != "POST":
        return JsonResponse({"ok": True})

    if not _verify_meta_signature(request):
        return HttpResponse("invalid signature", status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": True})

    # Extrai mensagens
    messages = _extract_messages_from_meta(payload)
    if not messages:
        return JsonResponse({"ok": True})

    today = timezone.localdate()

    for from_phone, message_text in messages:
        m = Manager.objects.filter(phone_e164=from_phone, is_active=True).first()
        if not m:
            continue

        checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=today)

        q = (
            OutboundQuestion.objects
            .filter(checkin=checkin, status="pending", answered_at__isnull=True)
            .order_by("scheduled_for")
            .first()
        )

        if q:
            q.answered_at = timezone.now()
            q.answer_text = message_text
            q.status = "answered"
            q.save(update_fields=["answered_at", "answer_text", "status"])

    return JsonResponse({"ok": True})