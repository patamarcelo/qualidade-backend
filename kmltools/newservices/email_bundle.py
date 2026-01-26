# kmltools/services/email_bundle.py
import io
import zipfile
from django.core.files.storage import default_storage

MAX_EMAIL_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20MB (seguro)

def build_job_zip_from_storage(job) -> tuple[bytes, str]:
    buf = io.BytesIO()

    zip_filename = f"kml_unifier_{job.request_id}.zip"

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # meta.json
        if job.meta_storage_path and default_storage.exists(job.meta_storage_path):
            with default_storage.open(job.meta_storage_path, "rb") as fp:
                z.writestr("meta.json", fp.read())

        # inputs
        for p in (job.input_storage_paths or []):
            if not p or not default_storage.exists(p):
                continue
            arcname = "inputs/" + p.split("/")[-1]
            with default_storage.open(p, "rb") as fp:
                z.writestr(arcname, fp.read())

        # output
        if job.storage_path and default_storage.exists(job.storage_path):
            with default_storage.open(job.storage_path, "rb") as fp:
                z.writestr("outputs/merged.kml", fp.read())

    data = buf.getvalue()
    if len(data) > MAX_EMAIL_ATTACHMENT_BYTES:
        raise ValueError(f"ZIP too large to attach: {len(data)} bytes")

    return data, zip_filename
