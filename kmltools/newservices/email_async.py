# kmltools/services/email_async.py
from threading import Thread
from django.utils import timezone

from kmltools.models import KMLMergeJob
from kmltools.newservices.email_bundle import build_job_zip_from_storage
from kmltools.newservices.mailer import send_job_zip_email


def _send_job_zip_email_thread(*, job_id: str, to_email: str, plan: str) -> None:
    try:
        job = KMLMergeJob.objects.get(id=job_id)

        has_inputs = bool(getattr(job, "input_storage_paths", None))
        has_meta = bool(getattr(job, "meta_storage_path", None))
        has_output = bool(getattr(job, "storage_path", None))

        if not (has_inputs and has_meta and has_output):
            # opcional: gravar erro no job
            if hasattr(job, "download_email_error"):
                job.download_email_error = "JOB_ARTIFACTS_MISSING_FOR_EMAIL"
                job.save(update_fields=["download_email_error"])
            return

        zip_bytes, zip_name = build_job_zip_from_storage(job)

        context = {
            "subject": "Your KML bundle is attached",
            "app_name": "KML Unifier",
            "user_email": to_email,
            "job_id": str(job.id),
            "request_id": getattr(job, "request_id", ""),
            "plan": plan,
            "total_files": getattr(job, "total_files", None),
            "total_polygons": getattr(job, "total_polygons", None),
        }

        send_job_zip_email(
            to_email,
            context=context,
            zip_bytes=zip_bytes,
            zip_filename=zip_name,
        )

        # auditoria (recomendado)
        if hasattr(job, "download_email_sent_at"):
            job.download_email_sent_at = timezone.now()
            job.save(update_fields=["download_email_sent_at"])

        # opcional: limpar erro anterior
        if hasattr(job, "download_email_error"):
            job.download_email_error = None
            job.save(update_fields=["download_email_error"])

    except Exception as e:
        # opcional: registrar erro
        try:
            job = KMLMergeJob.objects.get(id=job_id)
            if hasattr(job, "download_email_error"):
                job.download_email_error = f"{type(e).__name__}: {e}"
                job.save(update_fields=["download_email_error"])
        except Exception:
            pass


def queue_job_zip_email(*, job_id: str, to_email: str, plan: str) -> None:
    """
    Fire-and-forget. Não bloqueia o request.
    """
    Thread(
        target=_send_job_zip_email_thread,
        kwargs={"job_id": str(job_id), "to_email": to_email, "plan": plan},
        daemon=True,
    ).start()
