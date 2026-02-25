# opscheckin/views.py
import json
import hmac
import hashlib
import logging

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import Manager, DailyCheckin, OutboundQuestion
from .services.flow import create_and_send_next_question

logger = logging.getLogger("opscheckin.whatsapp")


def _verify_meta_signature(request) -> bool:
    """
    Recomendado em produção: valida X-Hub-Signature-256 com META_APP_SECRET.
    Se META_APP_SECRET não estiver setado, não bloqueia (MVP).
    """
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


def _extract_messages_from_meta(payload: dict):
    """
    Extrai (from_phone, text) do payload do WhatsApp Cloud API.
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
                    from_phone = (msg.get("from") or "").strip()  # ex: "5551999999999"
                    mtype = msg.get("type")

                    text = ""
                    if mtype == "text":
                        text = ((msg.get("text") or {}).get("body") or "").strip()
                    elif mtype == "button":
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
    # DEBUG básico
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

    # 1) Verificação do webhook (GET hub.challenge)
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

    messages = _extract_messages_from_meta(payload)
    if not messages:
        return JsonResponse({"ok": True})

    today = timezone.localdate()

    for from_phone, message_text in messages:
        m = Manager.objects.filter(phone_e164=from_phone, is_active=True).first()
        if not m:
            logger.warning("Mensagem ignorada: manager não encontrado from=%s", from_phone)
            continue

        checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=today)

        # pega a pergunta pendente mais antiga do dia
        q = (
            OutboundQuestion.objects
            .filter(checkin=checkin, status="pending", answered_at__isnull=True)
            .order_by("scheduled_for")
            .first()
        )

        if not q:
            logger.warning("Resposta recebida mas sem pergunta pending. manager=%s text=%s", m.id, message_text[:200])
            continue

        q.answered_at = timezone.now()
        q.answer_text = message_text
        q.status = "answered"
        q.save(update_fields=["answered_at", "answer_text", "status"])

        # MVP: assim que responde, já envia a próxima pergunta automaticamente (fluxo sequencial)
        create_and_send_next_question(m)

    return JsonResponse({"ok": True})