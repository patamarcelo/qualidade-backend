# gmail_api.py
import os
import base64
import pickle
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication



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

def get_gmail_service():
    """
    Retorna o service do Gmail usando refresh token e env vars.
    """
    creds = Credentials(
        token=None,  # será renovado automaticamente
        refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token"
    )
    service = build('gmail', 'v1', credentials=creds)
    return service

def send_mail_gmail_api(
    subject: str,
    body_html: str,
    from_email: str,
    to_emails: list,
    cc_emails: list = None,
    attachments: list = None,
    fail_silently: bool = False
):
    """
    Envia e-mail via Gmail API.
    
    :param subject: Assunto do e-mail
    :param body_html: Corpo em HTML
    :param from_email: Remetente
    :param to_emails: Lista de destinatários
    :param cc_emails: Lista de CC (opcional)
    :param attachments: Lista de tuplas (filename, bytes, mime_type) (opcional)
    :param fail_silently: Se True, não levanta exceção
    """
    try:
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        if cc_emails is None:
            cc_emails = []
        if attachments is None:
            attachments = []

        # Cria a mensagem multipart
        message = MIMEMultipart()
        message['to'] = ', '.join(to_emails)
        message['cc'] = ', '.join(cc_emails)
        message['from'] = from_email
        message['subject'] = subject

        # Corpo HTML
        message.attach(MIMEText(body_html, 'html'))

        # Anexos
        for filename, file_bytes, mime_type in attachments:
            part = MIMEApplication(file_bytes, _subtype=mime_type.split('/')[-1])
            part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            message.attach(part)

        # Codifica para enviar via Gmail API
        raw_message = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}

        # Envia
        service = get_gmail_service()
        result = service.users().messages().send(userId='me', body=raw_message).execute()
        return result

    except Exception as e:
        if not fail_silently:
            raise e