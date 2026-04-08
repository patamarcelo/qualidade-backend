# kmltools/emailer.py
import os
import resend

from django.template.loader import render_to_string
from django.utils.html import strip_tags

resend.api_key = os.getenv("RESEND_EMAIL_API_KEY_KMLUNIFIER")

FROM_EMAIL = "KML Unifier <team@kmlunifier.com>"

def send_kml_email(subject, html, to):
    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to if isinstance(to, list) else [to],
        "subject": subject,
        "html": html,
    })


def send_kml_templated_email(subject, template_name, context, to, text=None):
    html = render_to_string(template_name, context or {})
    plain_text = text or strip_tags(html)

    payload = {
        "from": FROM_EMAIL,
        "to": to if isinstance(to, list) else [to],
        "subject": subject,
        "html": html,
        "text": plain_text,
    }

    return resend.Emails.send(payload)


def send_reactivation_email(to):
    subject = "Turn multiple KML/KMZ polygon files into one single boundary"

    context = {
        "subject": subject,
        "cta_url": "https://kmlunifier.com/",
    }

    return send_kml_templated_email(
        subject=subject,
        template_name="email/reactivation_email.html",
        context=context,
        to=to,
    )