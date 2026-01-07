# kmltools/firebase_admin_init.py
import base64
import json
import os
import firebase_admin
from firebase_admin import credentials

def init_firebase_admin():
    """
    Inicializa o Firebase Admin SDK a partir de um JSON em base64
    (env: FIREBASE_SERVICE_ACCOUNT_B64).
    """
    if firebase_admin._apps:
        return

    b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64")
    if not b64:
        raise RuntimeError("Env FIREBASE_SERVICE_ACCOUNT_B64 não configurada.")

    raw = base64.b64decode(b64).decode("utf-8")
    data = json.loads(raw)

    cred = credentials.Certificate(data)
    firebase_admin.initialize_app(cred)
