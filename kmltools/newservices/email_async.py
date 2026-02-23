# kmltools/newservices/email_async.py
import os
import json
import base64
import zipfile
from io import BytesIO
from threading import Thread

import resend
from django.core.files.storage import default_storage
from django.utils import timezone

from kmltools.models import KMLMergeJob  # ajuste se o import estiver em outro app

resend.api_key = os.getenv("RESEND_EMAIL_API_KEY_KMLUNIFIER")

FROM_EMAIL = os.getenv("KML_DEFAULT_FROM", "KML Unifier <team@kmlunifier.com>")
REPLY_EMAIL = os.getenv("REPLY_EMAIL", "patamarcelo@gmail.com")


def _build_email_html(job: "KMLMergeJob", plan: str, download_url: str | None):
    # HTML simples, mas “bonito” e consistente
    btn = ""
    if download_url:
        btn = f"""
        <p style="margin:18px 0">
          <a href="{download_url}"
             style="display:inline-block;padding:12px 16px;border-radius:10px;
                    background:#4f46e5;color:#fff;text-decoration:none;font-weight:700">
            Download merged KML
          </a>
        </p>
        """

    created = ""
    try:
        created = job.created_at.astimezone(timezone.get_current_timezone()).strftime("%d/%m/%Y %H:%M")
    except Exception:
        created = ""

    return f"""
    <div style="font-family:Arial,sans-serif;line-height:1.45;color:#111;max-width:640px">
      <h2 style="margin:0 0 6px">Your KML Unifier files are ready</h2>
      <p style="margin:0 0 14px;color:#444">
        Job <b>{job.id}</b> {("• " + created) if created else ""}
      </p>

      {btn}

      <div style="padding:12px 14px;border:1px solid #e5e7eb;border-radius:12px;background:#fafafa">
        <div><b>Plan:</b> {plan}</div>
        <div><b>Files:</b> {job.total_files or 0}</div>
        <div><b>Polygons:</b> {job.total_polygons or 0}</div>
      </div>

      <p style="margin:14px 0 0;color:#444">
        Attached: <b>job_{job.id}.zip</b> (inputs + meta + output).
      </p>
      <p style="margin:10px 0 0;color:#666;font-size:13px">
        Need help? Just reply to this email.
      </p>
    </div>
    """


def _safe_read_storage(path: str) -> bytes | None:
    if not path:
        return None
    try:
        if not default_storage.exists(path):
            return None
        with default_storage.open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def _build_job_zip_bytes(job: "KMLMergeJob") -> bytes | None:
    """
    Cria ZIP em memória contendo:
      - output.kml (job.storage_path)
      - meta.json (job.meta_storage_path)
      - inputs/* (job.input_storage_paths)
    """
    buf = BytesIO()
    wrote_any = False

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # output
        out_bytes = _safe_read_storage(getattr(job, "storage_path", None))
        if out_bytes:
            zf.writestr("output.kml", out_bytes)
            wrote_any = True

        # meta
        meta_path = getattr(job, "meta_storage_path", None)
        meta_bytes = _safe_read_storage(meta_path)
        if meta_bytes:
            zf.writestr("meta.json", meta_bytes)
            wrote_any = True

        # inputs
        inputs = getattr(job, "input_storage_paths", None) or []
        for p in inputs:
            b = _safe_read_storage(p)
            if not b:
                continue
            # joga dentro de inputs/ com basename
            name = os.path.basename(p) or "input.kml"
            zf.writestr(f"inputs/{name}", b)
            wrote_any = True

    if not wrote_any:
        return None

    return buf.getvalue()


def _send_resend_email(to_email: str, subject: str, html: str, zip_bytes: bytes | None, zip_name: str):
    payload = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "replyTo": REPLY_EMAIL,
        "bcc": ["patamarcelo@gmail.com"],
    }

    if zip_bytes:
        payload["attachments"] = [
            {
                "filename": zip_name,
                "content": base64.b64encode(zip_bytes).decode("ascii"),
                # contentType opcional, mas ajuda alguns clients
                "contentType": "application/zip",
            }
        ]

    return resend.Emails.send(payload)


def _worker(job_id: str, to_email: str, plan: str):
    try:
        job = KMLMergeJob.objects.filter(id=job_id).first()
        if not job:
            print("[email_async] job not found:", job_id)
            return

        # URL direta do output (se seu storage suportar URL)
        download_url = None
        try:
            if getattr(job, "storage_path", None):
                download_url = default_storage.url(job.storage_path)
        except Exception:
            download_url = None

        subject = "Your KML Unifier files are ready"
        html = _build_email_html(job, plan, download_url)

        zip_bytes = _build_job_zip_bytes(job)
        zip_name = f"job_{job.id}.zip"

        _send_resend_email(to_email, subject, html, zip_bytes, zip_name)
        print("[email_async] sent via Resend ->", to_email, "job:", job_id, "zip:", bool(zip_bytes))

    except Exception as e:
        print("[email_async] failed sending via Resend:", type(e).__name__, str(e))


def queue_job_zip_email(job_id: str, to_email: str, plan: str):
    Thread(target=_worker, args=(job_id, to_email, plan), daemon=True).start()
    return True