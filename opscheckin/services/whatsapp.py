import logging
import requests
from django.conf import settings

logger = logging.getLogger("opscheckin.whatsapp")


def _get_api_version():
    return getattr(settings, "WHATSAPP_API_VERSION", "v25.0")


def _get_phone_number_id():
    return (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()


def _get_token():
    return (getattr(settings, "WHATSAPP_TOKEN", "") or "").strip()


def send_text(to_phone_e164: str, body: str) -> dict:
    """
    Envia mensagem de texto via WhatsApp Cloud API.
    `to_phone_e164`: ex "5551999999999" (wa_id / e164 sem +)
    """
    token = _get_token()
    phone_id = _get_phone_number_id()
    api_version = _get_api_version()

    if not token:
        raise RuntimeError("WHATSAPP_TOKEN não configurado")
    if not phone_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID não configurado")

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": str(to_phone_e164),
        "type": "text",
        "text": {"body": body},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=20)
    except requests.RequestException as e:
        logger.exception("WAPP_SEND_EXCEPTION to=%s err=%s", to_phone_e164, str(e))
        raise

    logger.warning(
        "WAPP_SEND status=%s to=%s body_len=%s",
        r.status_code,
        to_phone_e164,
        len(body or ""),
    )

    if r.status_code >= 400:
        logger.warning("WAPP_SEND_ERR response=%s", (r.text or "")[:2000])

    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": (r.text or "")[:4000]}