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
    body_params=None,          # list[str] posicional OU dict[str,str] nomeado
    header_params=None,        # list[str] ou dict[str,str]
    quick_reply_payloads=None, # list[str] na ordem dos botões
) -> dict:
    components = []

    def _build_text_parameters(params):
        if not params:
            return []

        if isinstance(params, dict):
            out = []
            for k, v in params.items():
                out.append(
                    {
                        "type": "text",
                        "parameter_name": str(k),
                        "text": str(v),
                    }
                )
            return out

        return [{"type": "text", "text": str(x)} for x in params]

    # HEADER
    header_parameters = _build_text_parameters(header_params)
    if header_parameters:
        components.append(
            {
                "type": "header",
                "parameters": header_parameters,
            }
        )

    # BODY
    body_parameters = _build_text_parameters(body_params)
    if body_parameters:
        components.append(
            {
                "type": "body",
                "parameters": body_parameters,
            }
        )

    # QUICK REPLY BUTTONS
    if quick_reply_payloads:
        for idx, payload in enumerate(quick_reply_payloads):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(idx),
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": str(payload),
                        }
                    ],
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



def send_buttons(
    to_phone_e164: str,
    *,
    header: str | None = None,
    body: str,
    footer: str | None = None,
    buttons: list[dict],  # [{"id":"AI:123:done","title":"✅ Feito"}, ...]
) -> dict:
    """
    Reply buttons: limite prático do WhatsApp é 3 botões.
    """
    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                for b in buttons
            ]
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to_phone_e164),
        "type": "interactive",
        "interactive": interactive,
    }
    return _post(payload, to_phone_e164=to_phone_e164)


def send_list(
    to_phone_e164: str,
    *,
    body: str,
    button_text: str,
    sections: list[dict],
    header: str | None = None,
    footer: str | None = None,
) -> dict:
    """
    Interactive List: ideal para selecionar 1 item dentre N.
    sections = [
      {"title": "Seção", "rows": [{"id":"X:1","title":"Item", "description":"..."}]}
    ]
    """
    interactive = {
        "type": "list",
        "body": {"text": body},
        "action": {"button": button_text, "sections": sections},
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to_phone_e164),
        "type": "interactive",
        "interactive": interactive,
    }
    return _post(payload, to_phone_e164=to_phone_e164)