import os
import uuid
import json
import xml.etree.ElementTree as ET
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
from .models import BillingProfile, WeeklyUsage, KMLMergeJob
from django.utils import timezone
from datetime import timedelta

from django.db import transaction
from django.db import IntegrityError


import os
import stripe
from rest_framework.exceptions import ValidationError
from datetime import datetime, timedelta, timezone as py_timezone  # <-- IMPORTANTE


from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404



FREE_WEEKLY_LIMIT = 2


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
            
            # ---- Persistir histórico do merge (metadata) ----
            try:
                input_filenames = [getattr(f, "name", "") for f in files]

                job = KMLMergeJob.objects.create(
                    user=request.user,
                    request_id=request_id,
                    plan=plan,
                    status=KMLMergeJob.STATUS_SUCCESS,
                    tol_m=tol_m,
                    corridor_width_m=corridor_width_m,
                    total_files=len(files),
                    total_polygons=total_polygons,

                    output_polygons=metrics.get("output_polygons"),
                    merged_polygons=metrics.get("merged_polygons"),

                    input_area_m2=metrics.get("input_area_m2"),
                    input_area_ha=metrics.get("input_area_ha"),
                    output_area_m2=metrics.get("output_area_m2"),
                    output_area_ha=metrics.get("output_area_ha"),

                    storage_path=saved_path,
                    metrics=metrics or {},
                    input_filenames=input_filenames,
                )
            except Exception as e:
                # Não quebrar o response por falha de histórico
                print(f"[KML_HISTORY] Falha ao salvar histórico do merge {request_id}: {e}")
                job = None

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
                
                "job_id": str(job.id) if job else None,
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        bp = getattr(request.user, "billing", None)

        if not bp:
            return Response({"email": request.user.email, "plan": "free"})

        # Só faz sync se fizer sentido
        if bp.plan == "pro" or bp.stripe_subscription_id:
            if bp.stripe_subscription_id:
                try:
                    sub = stripe.Subscription.retrieve(bp.stripe_subscription_id)

                    status_ = (sub.get("status") or "").lower().strip()
                    cpe_ts = sub.get("current_period_end")
                    cap = bool(sub.get("cancel_at_period_end") or False)

                    # Converte current_period_end (Stripe -> datetime UTC)
                    cpe = None
                    if cpe_ts:
                        cpe = timezone.datetime.fromtimestamp(int(cpe_ts), tz=py_timezone.utc)

                    # Atualiza campos locais (sem apagar deadline local se Stripe vier sem cpe)
                    if cpe:
                        bp.current_period_end = cpe
                    bp.cancel_at_period_end = cap

                    # Decide plano pelo status do Stripe
                    if status_ in ("active", "trialing"):
                        bp.plan = "pro"
                    else:
                        bp.plan = "free"
                        bp.current_period_end = None
                        bp.stripe_subscription_id = None
                        bp.cancel_at_period_end = False

                    bp.save(update_fields=[
                        "plan",
                        "current_period_end",
                        "stripe_subscription_id",
                        "cancel_at_period_end",
                        "updated_at",
                    ])

                except Exception:
                    # Se Stripe falhar, rebaixa por deadline local
                    if bp.current_period_end and timezone.now() > bp.current_period_end:
                        bp.plan = "free"
                        bp.current_period_end = None
                        bp.stripe_subscription_id = None
                        bp.cancel_at_period_end = False
                        bp.save(update_fields=[
                            "plan",
                            "current_period_end",
                            "stripe_subscription_id",
                            "cancel_at_period_end",
                            "updated_at",
                        ])

            else:
                # pro sem subscription_id => inconsistente
                bp.plan = "free"
                bp.current_period_end = None
                bp.cancel_at_period_end = False
                bp.save(update_fields=["plan", "current_period_end", "cancel_at_period_end", "updated_at"])

        return Response({
            "email": request.user.email,
            "plan": bp.plan,
            "current_period_end": bp.current_period_end.isoformat() if bp.current_period_end else None,
            "cancel_at_period_end": bp.cancel_at_period_end,
        })




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
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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

        # IMPORTANTE: em produção, APP_URL precisa ser https://kmlunifier.com
        # (não localhost). Esse é o URL que o Stripe vai redirecionar após o pagamento.
        app_url = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
        success_url = f"{app_url}/?stripe=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{app_url}/?stripe=cancel"

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
            client_reference_id=str(request.user.id),
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
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
            {"checkout_url": session["url"], "session_id": session["id"]},
            status=status.HTTP_200_OK,
        )



# =========================
# Helpers
# =========================

def _dt_from_unix(ts, label="ts"):
    """
    Converte unix timestamp (segundos) para datetime timezone-aware em UTC.
    NÃO usa django.utils.timezone.utc (não existe no Django 5).
    """
    if ts is None:
        return None
    try:
        ts_int = int(ts)
        return datetime.fromtimestamp(ts_int, tz=py_timezone.utc)
    except Exception as e:
        print(f"[stripe][dt] failed converting {label}={ts} ({type(ts)}) -> {e}")
        return None


def _add_months(dt, months: int):
    import calendar
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _derive_period_end_from_anchor(sub: dict):
    """
    Deriva deadline quando Stripe não manda current_period_end.
    Usa billing_cycle_anchor + intervalo do price (month/year).
    """
    anchor_ts = sub.get("billing_cycle_anchor") or sub.get("start_date") or sub.get("created")
    anchor = _dt_from_unix(anchor_ts, "billing_cycle_anchor|start_date|created")
    if not anchor:
        return None

    interval = None
    interval_count = 1

    try:
        items = (sub.get("items") or {}).get("data") or []
        if items:
            price = items[0].get("price") or {}
            recurring = price.get("recurring") or {}
            interval = recurring.get("interval")  # 'month' / 'year'
            interval_count = int(recurring.get("interval_count") or 1)
    except Exception:
        interval = None

    if interval == "month":
        return _add_months(anchor, interval_count)
    if interval == "year":
        return anchor.replace(year=anchor.year + interval_count)

    return anchor + timedelta(days=30)


def _extract_period_end_from_invoice(invoice: dict):
    """
    Pega o maior period.end das lines do invoice.
    """
    try:
        lines = (invoice.get("lines") or {}).get("data") or []
        ends = []
        for ln in lines:
            pe = (ln.get("period") or {}).get("end")
            dt = _dt_from_unix(pe, "invoice.lines.period.end")
            if dt:
                ends.append(dt)
        return max(ends) if ends else None
    except Exception as e:
        print("[stripe] failed extracting cpe from invoice:", str(e))
        return None


def _sync_bp_from_subscription(bp: BillingProfile, sub: dict, period_end_fallback=None):
    status_ = (sub.get("status") or "").lower().strip()

    raw_cpe = sub.get("current_period_end")
    raw_cap = sub.get("cancel_at_period_end")
    raw_cancel_at = sub.get("cancel_at")

    cpe = _dt_from_unix(raw_cpe, "sub.current_period_end")
    cancel_at_dt = _dt_from_unix(raw_cancel_at, "sub.cancel_at")

    # Fallbacks de deadline
    if not cpe and cancel_at_dt:
        cpe = cancel_at_dt
    if not cpe and period_end_fallback:
        cpe = period_end_fallback
    if not cpe:
        cpe = _derive_period_end_from_anchor(sub)

    # Boolean local: considerar flag OU a presença de cancel_at (seu Stripe está usando cancel_at)
    cap_local = bool(raw_cap) or bool(cancel_at_dt)

    bp.stripe_subscription_id = sub.get("id") or bp.stripe_subscription_id
    bp.current_period_end = cpe
    bp.cancel_at_period_end = cap_local

    now = timezone.now()

    # Regra de plano:
    # - active/trialing => pro
    # - caso contrário, se ainda existe deadline futura => pro até expirar
    # - senão => free
    if status_ in ("active", "trialing"):
        bp.plan = "pro"
    else:
        if cpe and cpe > now:
            bp.plan = "pro"
        else:
            bp.plan = "free"
            bp.current_period_end = None
            bp.stripe_subscription_id = None
            bp.cancel_at_period_end = False

    bp.save(update_fields=[
        "plan",
        "stripe_subscription_id",
        "current_period_end",
        "cancel_at_period_end",
        "updated_at",
    ])

    print(
        "[stripe][sync] saved -> plan:", bp.plan,
        "cpe:", bp.current_period_end,
        "cap(local):", bp.cancel_at_period_end,
        "status:", status_,
        "raw_cap:", raw_cap,
        "raw_cancel_at:", raw_cancel_at,
        "raw_cpe:", raw_cpe,
        "billing_cycle_anchor:", sub.get("billing_cycle_anchor"),
        "period_end_fallback:", period_end_fallback,
    )


# =========================
# Webhook
# =========================

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
        except Exception as e:
            print("[stripe] signature error:", str(e))
            return HttpResponse(status=400)

        event_type = event.get("type")
        obj = (event.get("data") or {}).get("object") or {}
        print("[stripe] event:", event_type)

        # 1) subscription created/updated
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            customer_id = obj.get("customer")
            sub_id = obj.get("id")
            print("[stripe] sub event:", event_type, "customer:", customer_id, "sub:", sub_id)

            if customer_id and sub_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp:
                    try:
                        # expand price para permitir derivação
                        sub = stripe.Subscription.retrieve(sub_id, expand=["items.data.price"])
                        _sync_bp_from_subscription(bp, sub)
                    except Exception as e:
                        print("[stripe] retrieve sub failed:", str(e))

            return HttpResponse(status=200)

        # 2) checkout.session.completed (garante sub_id e sincroniza)
        if event_type == "checkout.session.completed":
            customer_id = obj.get("customer")
            subscription_id = obj.get("subscription")
            print("[stripe] checkout completed customer:", customer_id, "sub:", subscription_id)

            if customer_id and subscription_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp:
                    bp.stripe_subscription_id = subscription_id
                    bp.plan = "pro"
                    bp.save(update_fields=["stripe_subscription_id", "plan", "updated_at"])

                    try:
                        sub = stripe.Subscription.retrieve(subscription_id, expand=["items.data.price"])
                        _sync_bp_from_subscription(bp, sub)
                    except Exception as e:
                        print("[stripe] checkout retrieve/sync failed:", str(e))

            return HttpResponse(status=200)

        # 3) invoice events (fallback)
        if event_type in ("invoice.paid", "invoice.payment_succeeded"):
            invoice = obj
            customer_id = invoice.get("customer")
            subscription_id = invoice.get("subscription")
            print("[stripe] invoice event:", event_type, "customer:", customer_id, "sub:", subscription_id)

            cpe_from_invoice = _extract_period_end_from_invoice(invoice)
            print("[stripe] cpe from invoice:", cpe_from_invoice)

            if customer_id and subscription_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp:
                    try:
                        sub = stripe.Subscription.retrieve(subscription_id, expand=["items.data.price"])
                        _sync_bp_from_subscription(bp, sub, period_end_fallback=cpe_from_invoice)
                    except Exception as e:
                        # mesmo sem subscription, salva ao menos deadline do invoice
                        print("[stripe] invoice retrieve sub failed:", str(e))
                        if cpe_from_invoice:
                            bp.plan = "pro"
                            bp.stripe_subscription_id = subscription_id
                            bp.current_period_end = cpe_from_invoice
                            bp.save(update_fields=["plan", "stripe_subscription_id", "current_period_end", "updated_at"])
                            print("[stripe] saved cpe from invoice only")

            return HttpResponse(status=200)

        # 4) subscription deleted (quando encerra de verdade)
        if event_type == "customer.subscription.deleted":
            customer_id = obj.get("customer")
            print("[stripe] subscription deleted customer:", customer_id)

            if customer_id:
                bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
                if bp:
                    bp.plan = "free"
                    bp.current_period_end = None
                    bp.stripe_subscription_id = None
                    bp.cancel_at_period_end = False
                    bp.save(update_fields=[
                        "plan", "current_period_end", "stripe_subscription_id", "cancel_at_period_end", "updated_at"
                    ])
                    print("[stripe] downgraded to free (deleted)")

            return HttpResponse(status=200)

        return HttpResponse(status=200)



class CreateBillingPortalSessionView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        bp = getattr(request.user, "billing", None)
        if not bp or not bp.stripe_customer_id:
            return Response(
                {"detail": "Stripe customer inexistente para este usuário.", "code": "STRIPE_CUSTOMER_MISSING"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # return_url: se vier do front, usa; senão usa APP_URL padrão
        body_return_url = None
        try:
            body_return_url = (request.data or {}).get("return_url")
        except Exception:
            body_return_url = None

        app_url = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
        return_url = (body_return_url or f"{app_url}/?stripe=portal_return").strip()

        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=bp.stripe_customer_id,
                return_url=return_url,
            )
        except stripe.error.StripeError as e:
            # Mostra mensagem útil para debug
            msg = getattr(e, "user_message", None) or str(e)
            return Response(
                {"detail": msg, "code": "STRIPE_PORTAL_ERROR"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"url": portal_session["url"]}, status=status.HTTP_200_OK)






class KMLHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class KMLHistoryView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        qs = KMLMergeJob.objects.filter(user=request.user).order_by("-created_at")

        # filtros opcionais
        status_ = (request.query_params.get("status") or "").strip().lower()
        if status_ in ("success", "error"):
            qs = qs.filter(status=status_)

        paginator = KMLHistoryPagination()
        page = paginator.paginate_queryset(qs, request)

        # serialização simples (sem criar Serializer por enquanto)
        items = []
        for job in page:
            try:
                url = default_storage.url(job.storage_path) if job.storage_path else None
            except Exception:
                url = None

            items.append({
                "id": str(job.id),
                "request_id": job.request_id,
                "status": job.status,
                "plan": job.plan,
                "created_at": job.created_at.isoformat(),

                "total_files": job.total_files,
                "total_polygons": job.total_polygons,
                "tol_m": job.tol_m,
                "corridor_width_m": job.corridor_width_m,

                "output_polygons": job.output_polygons,
                "merged_polygons": job.merged_polygons,
                "input_area_m2": job.input_area_m2,
                "input_area_ha": job.input_area_ha,
                "output_area_m2": job.output_area_m2,
                "output_area_ha": job.output_area_ha,

                "download_url": url,
                "input_filenames": job.input_filenames,
            })

        return paginator.get_paginated_response(items)


class KMLHistoryDownloadView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request, job_id):
        job = get_object_or_404(KMLMergeJob, id=job_id, user=request.user)

        if not job.storage_path:
            return Response({"detail": "Arquivo não disponível."}, status=status.HTTP_404_NOT_FOUND)

        try:
            url = default_storage.url(job.storage_path)
        except Exception:
            url = None

        if not url:
            return Response({"detail": "Não foi possível gerar a URL de download."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "id": str(job.id),
            "request_id": job.request_id,
            "download_url": url,
        }, status=status.HTTP_200_OK)
