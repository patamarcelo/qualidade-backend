# kmltools/authentication.py
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from firebase_admin import auth as fb_auth

from django.db import transaction, IntegrityError

from .models import BillingProfile
from .firebase_admin_init import init_firebase_admin


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

        email = (email or "").strip().lower()
        if not email:
            raise AuthenticationFailed("Email inválido no token.")

        User = get_user_model()

        # ✅ Fast path: achou BillingProfile pelo uid
        bp = BillingProfile.objects.select_related("user").filter(firebase_uid=uid).first()
        if bp and bp.user:
            return (bp.user, None)

        # ✅ Provisionamento idempotente (sem IntegrityError)
        try:
            with transaction.atomic():
                # 1) pega/cria usuário por email (idempotente)
                user = User.objects.filter(email=email).first()
                if not user:
                    user = User(email=email, username=email)
                    user.set_unusable_password()
                    user.save()

                if not user.username:
                    user.username = email
                    user.save(update_fields=["username"])

                # 2) garante BillingProfile
                bp, bp_created = BillingProfile.objects.get_or_create(
                    user=user,
                    defaults={"firebase_uid": uid, "plan": "free"},
                )

                # 3) se existe BillingProfile mas sem uid, seta
                if not bp.firebase_uid:
                    bp.firebase_uid = uid
                    bp.save(update_fields=["firebase_uid"])

                # 4) se firebase_uid é diferente, NÃO sobrescreve silenciosamente
                #    (isso evita linkar outra conta por acidente)
                elif bp.firebase_uid != uid:
                    raise AuthenticationFailed("Conta já vinculada a outro Firebase UID.")

        except IntegrityError:
            # Corrida rara: outro request criou ao mesmo tempo
            user = User.objects.filter(email=email).first()
            if not user:
                raise AuthenticationFailed("Erro ao provisionar usuário.")

            bp = BillingProfile.objects.filter(user=user).first()
            if bp and bp.firebase_uid and bp.firebase_uid != uid:
                raise AuthenticationFailed("Conta já vinculada a outro Firebase UID.")

            if bp and not bp.firebase_uid:
                bp.firebase_uid = uid
                bp.save(update_fields=["firebase_uid"])
            elif not bp:
                BillingProfile.objects.create(user=user, firebase_uid=uid, plan="free")

        return (user, None)
