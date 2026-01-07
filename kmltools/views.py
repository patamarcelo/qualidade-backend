import os
import uuid
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from threading import Thread

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from django.http import HttpResponse

from .services import merge_no_flood

from .authentication import FirebaseAuthentication
from rest_framework.permissions import IsAuthenticated
from .models import BillingProfile, WeeklyUsage
from django.utils import timezone

from django.db import transaction
from django.db import IntegrityError


import os
import stripe
from rest_framework.exceptions import ValidationError


FREE_WEEKLY_LIMIT = 3


def _debug_enabled():
    return str(getattr(settings, "KML_DEBUG_SAVE", "0")).lower() in ("1", "true", "yes")

def _save_kml_debug_bundle_storage(
    request_id: str,
    tol_m: float,
    corridor_width_m: float,
    files_bytes: list,
    kml_str: str,
    metrics: dict,
):
    """
    Salva bundle de debug usando default_storage (compatível com S3 / FileSystemStorage).

    Estrutura:
      kml_unions/kml_debug/<request_id>/
        meta.json
        inputs/<arquivo1.kml>
        inputs/<arquivo2.kml>
        output.kml
    """
    try:
        # garante que request_id não crie subpastas acidentalmente
        request_id_safe = (
            str(request_id)
            .replace("/", "_")
            .replace("\\", "_")
            .replace("..", "_")
            .strip()
        ) or uuid.uuid4().hex

        base = f"kml_unions/kml_debug/{request_id_safe}"

        payload = {
            "request_id": request_id_safe,
            "saved_at": datetime.now().isoformat(),
            "tol_m": tol_m,
            "corridor_width_m": corridor_width_m,
            "total_files": len(files_bytes),
            "files": [
                {"name": os.path.basename(n) or "input.kml", "size_bytes": len(b)}
                for n, b in files_bytes
            ],
            "metrics": metrics,
        }

        # meta.json
        default_storage.save(
            f"{base}/meta.json",
            ContentFile(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")),
        )

        # inputs
        for name, bts in files_bytes:
            safe = os.path.basename(name) or "input.kml"
            key = f"{base}/inputs/{safe}"

            # evita sobrescrever nomes repetidos
            if default_storage.exists(key):
                root, ext = os.path.splitext(safe)
                key = f"{base}/inputs/{root}_{uuid.uuid4().hex[:6]}{ext}"

            default_storage.save(key, ContentFile(bts))

        # output.kml
        default_storage.save(
            f"{base}/output.kml",
            ContentFile(kml_str.encode("utf-8")),
        )

    except Exception as e:
        print(f"[KML_DEBUG] Falha ao salvar bundle {request_id}: {e}")



class KMLUnionView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def clamp(self, value, min_value=None, max_value=None):
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    def post(self, request, *args, **kwargs):
        week_key = None
        weekly_used = None
        weekly_remaining = None
        usage = None

        
        
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"detail": "Nenhum arquivo enviado. Use o campo 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        bp = getattr(request.user, "billing", None)
        if not bp:
            return Response(
                {"detail": "BillingProfile ausente. Faça login novamente.", "code": "BILLING_PROFILE_MISSING"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        plan = bp.plan
        
        

        if plan == "free":
            today = timezone.localdate()
            year, week_num, _ = today.isocalendar()
            week_key = f"{year}{week_num:02d}"


            with transaction.atomic():
                try:
                    usage, _ = WeeklyUsage.objects.select_for_update().get_or_create(
                        user=request.user,
                        week=week_key,
                        defaults={"count": 0},
                    )
                except IntegrityError:
                    usage = WeeklyUsage.objects.select_for_update().get(user=request.user, week=week_key)

                if usage.count >= FREE_WEEKLY_LIMIT:
                    return Response(
                        {
                            "detail": "Limite semanal do plano gratuito atingido (3 unificações/semana).",
                            "code": "FREE_WEEKLY_LIMIT_REACHED",
                            "plan": "free",
                            "limit": FREE_WEEKLY_LIMIT,
                            "used": usage.count,
                            "week": week_key,
                            "weekly_remaining": 0,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
                usage.count += 1
                usage.save(update_fields=["count", "updated_at"])
                weekly_used = usage.count
                weekly_remaining = max(0, FREE_WEEKLY_LIMIT - weekly_used)
                
                
        request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        debug_enabled = _debug_enabled()

        # tol_m — mínimo 1
        try:
            tol_m = float(request.data.get("tol_m", 20.0))
            print("[TOL_M] tol_m received from FrontEnd:", tol_m)
        except (TypeError, ValueError):
            tol_m = 20.0
        tol_m = self.clamp(tol_m, min_value=1.0)

        # corridor_width_m — mínimo 1
        try:
            corridor_width_m = float(request.data.get("corridor_width_m", 1.0))
            print("[corridor_width_m] received from FrontEnd:", corridor_width_m)
        except (TypeError, ValueError):
            corridor_width_m = 1.0
        corridor_width_m = self.clamp(corridor_width_m, min_value=1.0)

        parcelas = []
        total_polygons = 0

        KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

        debug_files = []  # [(filename, bytes)]

        count = 1
        for uploaded in files:
            raw_bytes = uploaded.read()

            print("\n" + "=" * 60)
            print("arquivo recebido Nº:", count)
            count += 1
            print(f"📄 Recebido arquivo: {uploaded.name}")
            print(f"📦 Tamanho: {uploaded.size} bytes")
            print("-" * 60)
            try:
                snippet = raw_bytes[:500].decode("utf-8", errors="ignore")
            except Exception:
                snippet = str(raw_bytes[:200])
            print("🔍 Início do arquivo (snippet):")
            print(snippet)
            print("-" * 60)

            if debug_enabled:
                debug_files.append((uploaded.name, raw_bytes))

            poly_idx_file = 0
            try:
                root = ET.fromstring(raw_bytes)

                for placemark in root.findall(".//kml:Placemark", KML_NS):
                    name_el = placemark.find("kml:name", KML_NS)
                    talhao_name_base = (
                        name_el.text.strip()
                        if name_el is not None and name_el.text
                        else ""
                    )
                    if not talhao_name_base:
                        talhao_name_base = os.path.splitext(uploaded.name)[0]

                    poly_idx_pm = 0

                    for poly in placemark.findall(".//kml:Polygon", KML_NS):
                        coord_el = poly.find(
                            ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
                            KML_NS,
                        )
                        if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                            continue

                        coord_tokens = coord_el.text.strip().split()

                        coords = []
                        for token in coord_tokens:
                            parts = token.split(",")
                            if len(parts) < 2:
                                continue
                            try:
                                lon = float(parts[0])
                                lat = float(parts[1])
                            except ValueError:
                                continue
                            coords.append({"latitude": lat, "longitude": lon})

                        if not coords:
                            continue

                        poly_idx_pm += 1
                        poly_idx_file += 1
                        total_polygons += 1

                        talhao_name = (
                            talhao_name_base
                            if poly_idx_pm == 1
                            else f"{talhao_name_base}_{poly_idx_pm}"
                        )

                        parcelas.append({"talhao": talhao_name, "coords": coords})

                print(f"✅ Polígonos extraídos desse arquivo: {poly_idx_file}")

            except ET.ParseError as e:
                print(f"❌ Erro de parse XML em {uploaded.name}: {e}")
            except Exception as e:
                print(f"❌ Erro ao processar KML {uploaded.name}: {e}")

        print("=" * 60)
        print(f"📊 Total de polígonos extraídos de todos os arquivos: {total_polygons}")
        print(f"📊 Total de parcelas geradas: {len(parcelas)}")
        print("=" * 60)

        if not parcelas:
            return Response(
                {"detail": "Nenhum polígono válido encontrado nos arquivos KML.", "request_id": request_id},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            kml_str, metrics = merge_no_flood(
                parcelas,
                tol_m=tol_m,
                corridor_width_m=corridor_width_m,
                return_metrics=True,
            )
        except ValueError as e:
            return Response({"detail": str(e), "request_id": request_id}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"❌ Erro interno no merge_no_flood: {e}")
            return Response(
                {"detail": "Erro interno ao unificar polígonos.", "request_id": request_id},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # salva o KML final (como você já fazia)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kml_unions/union_{ts}_{uuid.uuid4().hex[:6]}.kml"
        saved_path = default_storage.save(filename, ContentFile(kml_str.encode("utf-8")))

        try:
            download_url = default_storage.url(saved_path)
        except NotImplementedError:
            media_url = settings.MEDIA_URL
            if not media_url.endswith("/"):
                media_url += "/"
            download_url = request.build_absolute_uri(media_url + saved_path)

        # debug em background (sem afetar o response)
        if debug_enabled:
            Thread(
                target=_save_kml_debug_bundle_storage,
                args=(request_id, tol_m, corridor_width_m, debug_files, kml_str, metrics),
                daemon=True,
            ).start()

        # ====== RESPOSTA: manter mesmo objeto “flat” do seu endpoint ======
        return Response(
            {
                "request_id": request_id,
                "download_url": download_url,
                "total_polygons": total_polygons,
                "total_files": len(files),
                "tol_m": tol_m,
                "corridor_width_m": corridor_width_m,

                # métricas como antes (flat)
                "output_polygons": metrics.get("output_polygons"),
                "merged_polygons": metrics.get("merged_polygons"),
                "input_area_m2": metrics.get("input_area_m2"),
                "input_area_ha": metrics.get("input_area_ha"),
                "output_area_m2": metrics.get("output_area_m2"),
                "output_area_ha": metrics.get("output_area_ha"),
                
                "plan": plan,
                "weekly_limit": FREE_WEEKLY_LIMIT if plan == "free" else None,
                "weekly_used": weekly_used if plan == "free" else None,
                "weekly_remaining": weekly_remaining if plan == "free" else None,
                "week": week_key if plan == "free" else None,
            },
            status=status.HTTP_200_OK,
        )

class MeView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        bp = getattr(request.user, "billing", None)

        return Response(
            {
                "email": request.user.email,
                "plan": bp.plan if bp else "free",
                "firebase_uid": bp.firebase_uid if bp else None,
            },
            status=status.HTTP_200_OK,
        )


class UsageView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        today = timezone.localdate()
        year, week_num, _ = today.isocalendar()
        week_key = f"{year}{week_num:02d}"

        used = (
            WeeklyUsage.objects.filter(user=request.user, week=week_key)
            .values_list("count", flat=True)
            .first()
        ) or 0

        remaining = max(0, FREE_WEEKLY_LIMIT - used)

        bp = getattr(request.user, "billing", None)
        plan = bp.plan if bp else "free"

        # Se pro, você pode retornar remaining=None (ilimitado)
        if plan != "free":
            return Response(
                {
                    "plan": plan,
                    "week": week_key,
                    "weekly_limit": None,
                    "weekly_used": used,  # opcional
                    "weekly_remaining": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "plan": "free",
                "week": week_key,
                "weekly_limit": FREE_WEEKLY_LIMIT,
                "weekly_used": used,
                "weekly_remaining": remaining,
            },
            status=status.HTTP_200_OK,
        )




stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class CreateCheckoutSessionView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # ou settings.STRIPE_SECRET_KEY
        bp = getattr(request.user, "billing", None)
        if not bp:
            return Response(
                {"detail": "BillingProfile ausente.", "code": "BILLING_PROFILE_MISSING"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        billing_cycle = (request.data.get("billing_cycle") or "").lower().strip()
        if billing_cycle not in ("monthly", "yearly"):
            raise ValidationError({"billing_cycle": "Use 'monthly' ou 'yearly'."})

        price_id = os.getenv("STRIPE_PRICE_ID_MONTHLY") if billing_cycle == "monthly" else os.getenv("STRIPE_PRICE_ID_YEARLY")
        if not price_id:
            return Response(
                {"detail": "Stripe price_id não configurado no servidor.", "code": "STRIPE_PRICE_ID_MISSING"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        app_url = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
        success_url = f"{app_url}/billing/success"
        cancel_url = f"{app_url}/billing/cancel"

        # garante customer
        if not bp.stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email,
                metadata={"firebase_uid": bp.firebase_uid, "django_user_id": str(request.user.id)},
            )
            bp.stripe_customer_id = customer["id"]
            bp.save(update_fields=["stripe_customer_id", "updated_at"])

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=bp.stripe_customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            allow_promotion_codes=True,
            subscription_data={
                "metadata": {
                    "firebase_uid": bp.firebase_uid,
                    "django_user_id": str(request.user.id),
                }
            },
            metadata={
                "firebase_uid": bp.firebase_uid,
                "django_user_id": str(request.user.id),
            },
        )

        return Response(
            {
                "checkout_url": session["url"],
                "session_id": session["id"],
            },
            status=status.HTTP_200_OK,
        )




class StripeWebhookView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


        if not endpoint_secret:
            return HttpResponse(status=500)

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except Exception:
            return HttpResponse(status=400)

        event_type = event["type"]
        data = event["data"]["object"]

        # 1) checkout.session.completed -> pega subscription e customer
        if event_type == "checkout.session.completed":
            customer_id = data.get("customer")
            subscription_id = data.get("subscription")

            if customer_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp and subscription_id:
                    bp.stripe_subscription_id = subscription_id
                    bp.plan = "pro"
                    bp.save(update_fields=["stripe_subscription_id", "plan", "updated_at"])

        # 2) invoice.paid -> atualiza período (mais confiável para renovação)
        if event_type == "invoice.paid":
            customer_id = data.get("customer")
            subscription_id = data.get("subscription")
            period_end = None

            # Stripe manda timestamps (unix) frequentemente
            lines = data.get("lines", {}).get("data", [])
            if lines:
                pe = lines[0].get("period", {}).get("end")
                if pe:
                    period_end = timezone.datetime.fromtimestamp(int(pe), tz=timezone.utc)

            if customer_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp:
                    bp.plan = "pro"
                    if subscription_id:
                        bp.stripe_subscription_id = subscription_id
                    if period_end:
                        bp.current_period_end = period_end
                    bp.save(update_fields=["plan", "stripe_subscription_id", "current_period_end", "updated_at"])

        # 3) customer.subscription.deleted -> volta para free
        if event_type == "customer.subscription.deleted":
            customer_id = data.get("customer")
            if customer_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp:
                    bp.plan = "free"
                    bp.current_period_end = None
                    bp.stripe_subscription_id = None
                    bp.save(update_fields=["plan", "current_period_end", "stripe_subscription_id", "updated_at"])

        return HttpResponse(status=200)
