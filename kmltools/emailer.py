import os
import resend

resend.api_key = os.getenv("RESEND_EMAIL_API_KEY_KMLUNIFIER")

FROM_EMAIL = "KML Unifier <team@kmlunifier.com>"

def send_kml_email(subject, html, to):
    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to if isinstance(to, list) else [to],
        "subject": subject,
        "html": html,
    })