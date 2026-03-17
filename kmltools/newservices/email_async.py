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
REPLY_EMAIL = "contact@kmlunifier.com"


def _fmt(n, digits=0):
    try:
        if n is None:
            return "-"
        n = float(n)
        if digits == 0:
            return f"{int(round(n)):,}".replace(",", ".")
        return f"{n:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "-"


def _build_email_html(job, plan: str, download_url: str | None):
    site_url = os.getenv("KML_SITE_URL", "https://kmlunifier.com").rstrip("/")
    support_email = "contact@kmlunifier.com"

    # métricas (podem ser None)
    tol_m = getattr(job, "tol_m", None)
    corridor = getattr(job, "corridor_width_m", None)
    total_files = getattr(job, "total_files", None)
    total_polygons = getattr(job, "total_polygons", None)
    out_polys = getattr(job, "output_polygons", None)
    merged_polys = getattr(job, "merged_polygons", None)
    in_ha = getattr(job, "input_area_ha", None)
    out_ha = getattr(job, "output_area_ha", None)

    # data local (se quiser)
    created_txt = ""
    try:
        created = job.created_at.astimezone(timezone.get_current_timezone())
        created_txt = created.strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass

    # preheader (texto “oculto” que melhora open-rate)
    preheader = "Your merged KML is ready — download link + ZIP attached."

    button_block = ""
    if download_url:
        button_block = f"""
          <div style="margin:18px 0 6px">
            <a href="{download_url}"
              style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;
                     padding:12px 16px;border-radius:12px;font-weight:800">
              Download merged KML
            </a>
          </div>
          <div style="color:#6b7280;font-size:13px">
            Or open the site: <a href="{site_url}" style="color:#4f46e5;text-decoration:none">{site_url}</a>
          </div>
        """

    return f"""
<!doctype html>
<html>
  <body style="margin:0;background:#f6f7fb;padding:24px">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">
      {preheader}
    </div>

    <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:16px;
                border:1px solid #e5e7eb;box-shadow:0 8px 30px rgba(0,0,0,0.06);
                overflow:hidden;font-family:Arial,sans-serif;color:#111827">

      <div style="padding:18px 20px;background:linear-gradient(90deg,#111827,#1f2937);color:#fff">
        <div style="font-size:14px;opacity:.92">KML Unifier</div>
        <div style="font-size:22px;font-weight:900;margin-top:4px">Your files are ready</div>
        <div style="font-size:13px;opacity:.82;margin-top:6px">
          Job <b>{job.id}</b>{(" • " + created_txt) if created_txt else ""} • Plan <b>{plan}</b>
        </div>
      </div>

      <div style="padding:18px 20px">
        <p style="margin:0 0 12px;color:#374151">
          Your merged boundary is ready. We attached a ZIP with the original inputs, metadata and the final output.
        </p>

        {button_block}

        <div style="margin:16px 0 0;padding:14px;border:1px solid #e5e7eb;border-radius:14px;background:#fafafa">
          <div style="font-weight:800;margin-bottom:10px">Job details</div>

          <table style="width:100%;border-collapse:collapse;font-size:14px;color:#111827">
            <tr>
              <td style="padding:6px 0;color:#6b7280;width:48%">Files uploaded</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(total_files)}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Polygons detected</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(total_polygons)}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Output polygons</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(out_polys)}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Merged polygons</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(merged_polys)}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Tolerance</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(tol_m)} m</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Corridor width</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(corridor)} m</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Input area</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(in_ha, 2)} ha</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#6b7280">Output area</td>
              <td style="padding:6px 0;font-weight:700">{_fmt(out_ha, 2)} ha</td>
            </tr>
          </table>
        </div>

        <div style="margin:14px 0 0;padding:12px 14px;border-radius:14px;border:1px dashed #c7d2fe;background:#eef2ff">
          <div style="font-weight:800;color:#3730a3;margin-bottom:6px">Attachment</div>
          <div style="color:#3730a3;font-size:13px">
            job_{job.id}.zip (inputs + meta + output.kml)
          </div>
        </div>

        <div style="margin-top:16px;color:#6b7280;font-size:13px;line-height:1.5">
          Need help? Reply to this email or contact:
          <a href="mailto:{support_email}" style="color:#4f46e5;text-decoration:none">{support_email}</a>
          <br/>
          Website:
          <a href="{site_url}" style="color:#4f46e5;text-decoration:none">{site_url}</a>
        </div>
      </div>

      <div style="padding:14px 20px;border-top:1px solid #e5e7eb;background:#fcfcfd;color:#9ca3af;font-size:12px">
        Sent by KML Unifier • {site_url}
      </div>
    </div>
  </body>
</html>
""".strip()


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