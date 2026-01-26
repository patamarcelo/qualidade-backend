# kmltools/views_feedback.py
from django.conf import settings
from django.utils.html import escape

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import KMLMergeJob, MergeFeedback

# ✅ use a MESMA autenticação do MeView (ajuste o import conforme seu projeto)
from .authentication import FirebaseAuthentication  # <-- ajuste se o caminho for outro

from diamante.gmail.gmail_api import send_mail_gmail_api


def _notify_feedback_email(user_email: str, job: KMLMergeJob, message: str):
    notify_to = getattr(settings, "KML_FEEDBACK_NOTIFY_TO", None) or "patamarcelo@gmail.com"

    subject = f"[KMLUnifier] New feedback - job {job.id} - {user_email or 'unknown'}"

    body_html = f"""
    <div style="font-family:Arial, sans-serif; font-size:14px;">
      <h3 style="margin:0 0 8px 0;">New merge feedback</h3>
      <p style="margin:0 0 12px 0;">
        <b>User:</b> {escape(user_email or "")}<br/>
        <b>Job ID:</b> {escape(str(job.id))}<br/>
        <b>Request ID:</b> {escape(job.request_id)}<br/>
        <b>Status:</b> {escape(job.status)}<br/>
        <b>Plan:</b> {escape(job.plan)}<br/>
        <b>Created:</b> {escape(str(job.created_at))}
      </p>

      <div style="border:1px solid #eee; border-radius:10px; padding:12px; background:#fafafa;">
        <div style="font-weight:700; margin-bottom:6px;">Message</div>
        <div style="white-space:pre-wrap;">{escape(message)}</div>
      </div>
    </div>
    """

    # ✅ envia, mas não quebra o fluxo se falhar
    send_mail_gmail_api(
        subject=subject,
        body_html=body_html,
        from_email="no-reply@kmlunifier.com",
        to_emails=[notify_to],
        fail_silently=True,
    )


class MergeFeedbackView(APIView):
    """
    POST /kmltools/feedback/

    Body:
      - merge_job_id: UUID (string)
      - message: string
      - source: optional string (default "ui")
    """
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        merge_job_id = request.data.get("merge_job_id")
        message = (request.data.get("message") or "").strip()
        source = (request.data.get("source") or "ui").strip()[:32]

        if not merge_job_id:
            return Response({"detail": "merge_job_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        if len(message) < 5:
            return Response({"detail": "message is too short."}, status=status.HTTP_400_BAD_REQUEST)

        if len(message) > 2000:
            return Response({"detail": "message is too long."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ garante que o job é do usuário logado
        try:
            job = KMLMergeJob.objects.get(id=merge_job_id, user=request.user)
        except KMLMergeJob.DoesNotExist:
            return Response({"detail": "Merge job not found."}, status=status.HTTP_404_NOT_FOUND)

        # ✅ 1 feedback por job (opcional)
        if MergeFeedback.objects.filter(user=request.user, merge_job=job).exists():
            return Response({"detail": "Feedback already sent for this merge."}, status=status.HTTP_409_CONFLICT)

        feedback = MergeFeedback.objects.create(
            user=request.user,
            merge_job=job,
            message=message,
            source=source,
        )

        # ✅ notifica por e-mail (não quebra o usuário)
        try:
            user_email = getattr(request.user, "email", "") or ""
            _notify_feedback_email(user_email=user_email, job=job, message=message)
        except Exception:
            pass

        return Response(
            {
                "ok": True,
                "id": feedback.id,
                "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
            },
            status=status.HTTP_201_CREATED,
        )
