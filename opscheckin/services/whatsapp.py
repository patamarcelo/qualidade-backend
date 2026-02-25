import requests
from django.conf import settings

GRAPH_URL = (
    f"https://graph.facebook.com/"
    f"{settings.WHATSAPP_API_VERSION}/"
    f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
)


def send_text(to_e164: str, body: str) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "text",
        "text": {"body": body},
    }

    response = requests.post(GRAPH_URL, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()