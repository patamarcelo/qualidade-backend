# opscheckin/services/whatsapp.py
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


def _post(payload: dict, *, to_phone_e164: str, timeout: int = 20) -> dict:
    token = _get_token()
    phone_id = _get_phone_number_id()
    api_version = _get_api_version()

    if not token:
        raise RuntimeError("WHATSAPP_TOKEN não configurado")
    if not phone_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID não configurado")

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        logger.exception("WAPP_SEND_EXCEPTION to=%s err=%s", to_phone_e164, str(e))
        raise

    logger.warning("WAPP_SEND status=%s to=%s", r.status_code, to_phone_e164)

    if r.status_code >= 400:
        logger.warning("WAPP_SEND_ERR response=%s", (r.text or "")[:2000])

    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": (r.text or "")[:4000]}


def send_text(to_phone_e164: str, body: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": str(to_phone_e164),
        "type": "text",
        "text": {"body": body},
    }
    return _post(payload, to_phone_e164=to_phone_e164)


def send_template(
    to_phone_e164: str,
    *,
    template_name: str,
    language_code: str = "pt_BR",
    body_params: list[str] | None = None,
) -> dict:
    """
    Envia template aprovado para re-engagement (fora da janela de 24h).
    body_params vira parâmetros do componente BODY ({{1}}, {{2}}...).
    """
    components = []
    if body_params:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(x)} for x in body_params],
            }
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to_phone_e164),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            **({"components": components} if components else {}),
        },
    }
    return _post(payload, to_phone_e164=to_phone_e164)