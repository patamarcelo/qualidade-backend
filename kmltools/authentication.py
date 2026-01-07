# kmltools/authentication.py
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from firebase_admin import auth as fb_auth

from .models import BillingProfile
from .firebase_admin_init import init_firebase_admin


from django.db import transaction, IntegrityError

class FirebaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        init_firebase_admin()

        header = request.headers.get("Authorization") or ""
        if not header.startswith("Bearer "):
            return None

        id_token = header.split("Bearer ", 1)[1].strip()
        if not id_token:
            raise AuthenticationFailed("Token ausente.")

        try:
            decoded = fb_auth.verify_id_token(id_token)
        except Exception:
            raise AuthenticationFailed("Token inválido ou expirado.")

        uid = decoded.get("uid")
        email = decoded.get("email")

        if not uid:
            raise AuthenticationFailed("Token sem uid.")
        if not email:
            raise AuthenticationFailed("Token sem email.")

        User = get_user_model()

        # Fast path
        bp = BillingProfile.objects.select_related("user").filter(firebase_uid=uid).first()
        if bp:
            return (bp.user, None)

        # Provisionamento seguro
        with transaction.atomic():
            user = User.objects.select_for_update().filter(email=email).first()
            if not user:
                user = User.objects.create_user(email=email, password=None)

            bp, _ = BillingProfile.objects.get_or_create(
                user=user,
                defaults={"firebase_uid": uid, "plan": "free"},
            )

            # Se já existia por user, mas uid não estava setado/correto, atualiza
            if bp.firebase_uid != uid:
                # aqui você decide a política:
                # - se permitir update (recomendado quando você sabe que é o mesmo email)
                # - ou bloquear por segurança
                bp.firebase_uid = uid
                bp.save(update_fields=["firebase_uid"])

        return (user, None)
