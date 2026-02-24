# whatsapp.py
import requests
from django.conf import settings

def send_whatsapp_text(to_e164: str, text: str):
    """
    Stub. Substituir pelo seu provedor.
    """
    # Exemplo (pseudo): requests.post(...)

    # IMPORTANTE: sempre logar o response / status
    return {"ok": True}