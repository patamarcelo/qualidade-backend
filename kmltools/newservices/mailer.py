# kmltools/services/mailer.py
from django.conf import settings
from django.template.loader import render_to_string

# ajuste o import conforme seu projeto (ex: "from kmltools.gmail_api import send_mail_gmail_api")
from diamante.gmail.gmail_api import send_mail_gmail_api


def send_job_zip_email(to_email: str, *, context: dict, zip_bytes: bytes, zip_filename: str) -> None:
    """
    Envia e-mail com ZIP anexado usando Gmail API (funções já existentes em gmail_api.py).
    - Mantém template HTML e TXT.
    - Usa send_mail_gmail_api para suportar anexos.
    """
    subject = context.get("subject") or "Your KML files (inputs + output) are ready"

    # Mantém os templates (TXT pode ser usado como fallback/preview; Gmail API aqui envia HTML)
    _ = render_to_string("email/kml_bundle.txt", context)  # opcional: manter para debug/consistência
    html_body = render_to_string("email/kml_bundle.html", context)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "patamarcelo@gmail.com"

    # Anexo ZIP
    attachments = [
        (zip_filename, zip_bytes, "application/zip"),
    ]

    send_mail_gmail_api(
        subject=subject,
        body_html=html_body,
        from_email=from_email,
        to_emails=[to_email],
        cc_emails=[],
        attachments=attachments,
        fail_silently=False,
    )
