from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from firebase_admin import auth as fb_auth

from .firebase_admin_init import init_firebase_admin
from .models import BillingProfile, EmailMagicLink
from .newservices.magic_link_email import send_magic_login_email


def normalize_email(email):
    return (email or "").strip().lower()


def get_client_ip(request):
    cf = (request.META.get("HTTP_CF_CONNECTING_IP") or "").strip()
    if cf:
        return cf

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()

    return (
        request.META.get("HTTP_X_REAL_IP")
        or request.META.get("REMOTE_ADDR")
        or ""
    ).strip() or None


class RequestEmailMagicLinkView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        email = normalize_email(request.data.get("email"))
        redirect_url = (request.data.get("redirect_url") or "").strip()

        if not email or "@" not in email:
            return Response(
                {"detail": "Invalid email address.", "code": "INVALID_EMAIL"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not redirect_url:
            return Response(
                {"detail": "Missing redirect_url.", "code": "MISSING_REDIRECT_URL"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_token = EmailMagicLink.make_raw_token()
        token_hash = EmailMagicLink.hash_token(raw_token)

        EmailMagicLink.objects.create(
            email=email,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(minutes=30),
            ip_address=get_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:2000],
        )

        separator = "&" if "?" in redirect_url else "?"
        link = f"{redirect_url}{separator}{urlencode({'token': raw_token})}"

        try:
            send_magic_login_email(to_email=email, link=link)
        except Exception as e:
            return Response(
                {
                    "detail": "Could not send login email.",
                    "code": "EMAIL_SEND_FAILED",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class VerifyEmailMagicLinkView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        raw_token = (request.data.get("token") or "").strip()

        if not raw_token:
            return Response(
                {"detail": "Missing token.", "code": "MISSING_TOKEN"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token_hash = EmailMagicLink.hash_token(raw_token)

        with transaction.atomic():
            magic = (
                EmailMagicLink.objects
                .select_for_update()
                .filter(token_hash=token_hash)
                .first()
            )

            if not magic or not magic.is_valid():
                return Response(
                    {
                        "detail": "Invalid or expired login link.",
                        "code": "INVALID_OR_EXPIRED_LINK",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            email = normalize_email(magic.email)

            init_firebase_admin()

            try:
                fb_user = fb_auth.get_user_by_email(email)
            except fb_auth.UserNotFoundError:
                fb_user = fb_auth.create_user(
                    email=email,
                    email_verified=True,
                    disabled=False,
                )

            firebase_uid = fb_user.uid

            if not getattr(fb_user, "email_verified", False):
                fb_auth.update_user(firebase_uid, email_verified=True)

            User = get_user_model()

            user = User.objects.filter(email=email).first()
            if not user:
                user = User(email=email, username=email, origin_app="kmltools")
                user.set_unusable_password()
                user.save()

            if not user.username:
                user.username = email
                user.save(update_fields=["username"])

            bp, _ = BillingProfile.objects.get_or_create(
                user=user,
                defaults={
                    "firebase_uid": firebase_uid,
                    "plan": "free",
                },
            )

            if not bp.firebase_uid:
                bp.firebase_uid = firebase_uid
                bp.save(update_fields=["firebase_uid", "updated_at"])
            elif bp.firebase_uid != firebase_uid:
                return Response(
                    {
                        "detail": "This account is already linked to another Firebase user.",
                        "code": "FIREBASE_UID_CONFLICT",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            magic.used_at = timezone.now()
            magic.firebase_uid = firebase_uid
            magic.save(update_fields=["used_at", "firebase_uid"])

        custom_token = fb_auth.create_custom_token(firebase_uid).decode("utf-8")

        return Response(
            {
                "ok": True,
                "custom_token": custom_token,
                "email": email,
                "firebase_uid": firebase_uid,
            },
            status=status.HTTP_200_OK,
        )