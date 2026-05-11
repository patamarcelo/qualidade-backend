# kmltools/newservices/recovery_email.py

import os
import resend

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from kmltools.models import KMLMergeJob


resend.api_key = os.getenv("RESEND_EMAIL_API_KEY_KMLUNIFIER")

FROM_EMAIL = os.getenv(
    "KML_DEFAULT_FROM",
    getattr(settings, "DEFAULT_FROM_EMAIL", "KML Unifier <team@kmlunifier.com>"),
)

REPLY_EMAIL = os.getenv(
    "KML_REPLY_EMAIL",
    getattr(settings, "KML_SUPPORT_EMAIL", "team@kmlunifier.com"),
)


def build_kml_result_url(job):
    """
    URL para trazer o usuário de volta ao resultado.

    Se você configurar KML_RESULT_URL_TEMPLATE:
      KML_RESULT_URL_TEMPLATE = "https://kmlunifier.com/account/jobs?job={job_id}&recover=1"

    Caso contrário, usa APP_URL como fallback.
    """
    template = getattr(settings, "KML_RESULT_URL_TEMPLATE", "") or os.getenv("KML_RESULT_URL_TEMPLATE", "")

    if template:
        return template.format(
            job_id=str(job.id),
            request_id=job.request_id,
        )

    app_url = (
        os.getenv("KML_SITE_URL")
        or getattr(settings, "APP_URL", "https://kmlunifier.com")
        or "https://kmlunifier.com"
    ).rstrip("/")

    # Por enquanto, prefiro mandar para a tela existente de conta/jobs.
    # Se a rota real no front for outra, ajuste aqui.
    return f"{app_url}/account/jobs?job={job.id}&recover=1"


def get_kml_recovery_block_reason(job):
    """
    Retorna None se puder enviar.
    Caso contrário, retorna o motivo do bloqueio.
    """
    if not job:
        return "Job inválido."

    if job.status != KMLMergeJob.STATUS_SUCCESS:
        return "Job ainda não está finalizado com sucesso."

    if not job.user_id:
        return "Job não tem usuário vinculado."

    email = (getattr(job.user, "email", "") or "").strip()
    if not email:
        return "Usuário não tem e-mail."

    if getattr(job, "download_unlocked", False):
        return "Download já foi desbloqueado."

    if getattr(job, "first_downloaded_at", None):
        return "Arquivo já foi baixado."

    if int(getattr(job, "download_count", 0) or 0) > 0:
        return "Arquivo já tem download registrado."

    if getattr(job, "recovery_email_sent_at", None):
        return "E-mail de recuperação já foi enviado."

    return None


def _render_recovery_email(job, *, result_url, test_to_email=None):
    input_filenames = job.input_filenames or []
    if not isinstance(input_filenames, list):
        input_filenames = []

    context = {
        "job": job,
        "user": job.user,
        "result_url": result_url,
        "support_email": REPLY_EMAIL,
        "total_files": int(job.total_files or 0),
        "total_polygons": int(job.total_polygons or 0),
        "output_polygons": job.output_polygons,
        "output_area_ha": job.output_area_ha,
        "input_filenames": input_filenames[:6],
        "is_test": bool(test_to_email),
    }

    text_body = render_to_string(
        "kmltools/emails/kml_ready_recovery.txt",
        context,
    )

    html_body = render_to_string(
        "kmltools/emails/kml_ready_recovery.html",
        context,
    )

    return text_body, html_body


def send_kml_ready_recovery_email(job, *, sent_by=None, test_to_email=None, mark_as_sent=True):
    """
    Envia recovery email usando Resend.

    - Envio real:
      valida elegibilidade e marca recovery_email_sent_at.

    - Envio de teste:
      envia para o admin, não marca como enviado.
    """
    if not resend.api_key:
        return {
            "ok": False,
            "sent": False,
            "blocked": False,
            "reason": "RESEND_EMAIL_API_KEY_KMLUNIFIER não configurada.",
        }

    is_test = bool(test_to_email)

    if is_test:
        to_email = (test_to_email or "").strip()
        mark_as_sent = False
    else:
        block_reason = get_kml_recovery_block_reason(job)
        if block_reason:
            return {
                "ok": False,
                "sent": False,
                "blocked": True,
                "reason": block_reason,
            }

        to_email = (getattr(job.user, "email", "") or "").strip()

    if not to_email:
        return {
            "ok": False,
            "sent": False,
            "blocked": True,
            "reason": "E-mail de destino ausente.",
        }

    result_url = build_kml_result_url(job)

    subject = "Your merged KML file is ready"
    if is_test:
        subject = f"[TEST] {subject}"

    try:
        text_body, html_body = _render_recovery_email(
            job,
            result_url=result_url,
            test_to_email=test_to_email,
        )

        resend_result = resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "replyTo": REPLY_EMAIL,
        })

        if mark_as_sent:
            with transaction.atomic():
                locked_job = KMLMergeJob.objects.select_for_update().get(pk=job.pk)

                # Revalida depois do envio para evitar clique duplo ou mudança de estado.
                block_reason = get_kml_recovery_block_reason(locked_job)
                if block_reason:
                    return {
                        "ok": False,
                        "sent": True,
                        "marked": False,
                        "blocked": True,
                        "reason": f"E-mail enviado, mas não marcado: {block_reason}",
                        "result": resend_result,
                    }

                locked_job.recovery_email_sent_at = timezone.now()
                locked_job.recovery_email_sent_to = to_email
                locked_job.recovery_email_last_error = ""
                locked_job.save(
                    update_fields=[
                        "recovery_email_sent_at",
                        "recovery_email_sent_to",
                        "recovery_email_last_error",
                    ]
                )

        return {
            "ok": True,
            "sent": True,
            "to": to_email,
            "result_url": result_url,
            "test": is_test,
            "marked": bool(mark_as_sent),
            "result": resend_result,
        }

    except Exception as exc:
        error_message = str(exc)[:2000]

        try:
            job.recovery_email_last_error = error_message
            job.save(update_fields=["recovery_email_last_error"])
        except Exception:
            pass

        return {
            "ok": False,
            "sent": False,
            "blocked": False,
            "reason": error_message,
        }