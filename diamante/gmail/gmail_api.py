# gmail_api.py
import os
import base64
import pickle
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials


SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Gera token usando env vars (client_id / client_secret)
def generate_token():
    client_config = {
        "installed": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)
    return creds

# Função send_mail compatível com Django
def send_mail(subject, message, from_email, recipient_list, fail_silently=False):
    try:
        # Cria credenciais usando refresh token e client_id / client_secret das env vars
        creds = Credentials(
            token=None,  # Será renovado pelo refresh_token
            refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
            client_id=os.environ.get("GOOGLE_CLIENT_ID"),
            client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token"
        )

        service = build('gmail', 'v1', credentials=creds)

        # Garante que recipient_list seja uma lista
        if isinstance(recipient_list, str):
            recipient_list = [recipient_list]

        # Monta a mensagem MIME
        mime_message = MIMEText(message, "html")
        mime_message['to'] = ', '.join(recipient_list)
        mime_message['from'] = from_email
        mime_message['subject'] = subject

        # Codifica em base64
        raw_message = {'raw': base64.urlsafe_b64encode(mime_message.as_bytes()).decode()}

        # Envia a mensagem
        result = service.users().messages().send(userId='me', body=raw_message).execute()
        return result

    except Exception as e:
        if not fail_silently:
            raise e