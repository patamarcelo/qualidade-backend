import os
import uuid
import json
import xml.etree.ElementTree as ET
from threading import Thread
from datetime import datetime, timedelta, timezone as py_timezone

import stripe

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import FirebaseAuthentication
from .models import BillingProfile, WeeklyUsage, KMLMergeJob
from kmltools.services import merge_no_flood, merge_no_flood_not_union
from kmltools.newservices.credits import reserve_one_credit, refund_one_credit, NoCreditsLeft


from django.utils.text import slugify
from .newservices.email_async import queue_job_zip_email






import zipfile
from io import BytesIO






import re

import zipfile
from io import BytesIO

from urllib.parse import urlparse


import requests


from django.core.cache import cache







# aceita href com texto direto OU com <![CDATA[...]]>
NETWORKLINK_HREF_RE = re.compile(
    r"<href>\s*(?:<!\[CDATA\[)?\s*([^<\]\s]+)\s*(?:\]\]>)?\s*</href>",
    re.IGNORECASE,
)




# Ajuste a allowlist conforme você quiser (MVP seguro)
DEFAULT_ALLOWED_HOST_SUFFIXES = (
    "google.com",
    "googleusercontent.com",
    "maps.google.com",
    "www.google.com",
)

# limites “anti-surpresa” (performance)
DEFAULT_MAX_REMOTE_BYTES = 8 * 1024 * 1024  # 8MB
DEFAULT_CONNECT_TIMEOUT = 3
DEFAULT_READ_TIMEOUT = 6
DEFAULT_MAX_REDIRECTS = 3
DEFAULT_CACHE_TTL_SECONDS = 60 * 60  # 1h


class NetworkLinkResolveError(Exception):
    pass




FREE_MONTHLY_CREDITS = 0
PREPAID_CREDITS_PER_PACK = 10



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

class MeView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        bp = getattr(request.user, "billing", None)
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        if not bp:
            return Response({"email": request.user.email, "plan": "free"})

        # Só faz sync se fizer sentido
        if bp.plan in ("pro_monthly", "pro_yearly") or bp.stripe_subscription_id:
            if bp.stripe_subscription_id:
                try:
                    sub = stripe.Subscription.retrieve(bp.stripe_subscription_id)

                    status_ = (sub.get("status") or "").lower().strip()
                    cpe_ts = sub.get("current_period_end")
                    cap = bool(sub.get("cancel_at_period_end") or False)

                    cpe = None
                    if cpe_ts:
                        cpe = timezone.datetime.fromtimestamp(int(cpe_ts), tz=py_timezone.utc)

                    if cpe:
                        bp.current_period_end = cpe
                    bp.cancel_at_period_end = cap

                    # determina intervalo (month/year)
                    interval = None
                    try:
                        items = (sub.get("items") or {}).get("data") or []
                        if items:
                            price = items[0].get("price") or {}
                            recurring = price.get("recurring") or {}
                            interval = (recurring.get("interval") or "").lower().strip()
                    except Exception:
                        interval = None

                    if status_ in ("active", "trialing"):
                        bp.plan = "pro_yearly" if interval == "year" else "pro_monthly"
                    else:
                        if bp.plan in ("pro_monthly", "pro_yearly"):
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
                        if bp.plan in ("pro_monthly", "pro_yearly"):
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
                # pro_* sem subscription_id => inconsistente
                if bp.plan in ("pro_monthly", "pro_yearly"):
                    bp.plan = "free"
                bp.current_period_end = None
                bp.cancel_at_period_end = False
                bp.save(update_fields=["plan", "current_period_end", "cancel_at_period_end", "updated_at"])

        # Para UX: se free, garante reset mensal (não cumulativo) ao consultar
        if bp.plan == "free":
            bp.reset_free_monthly_if_needed(monthly_amount=FREE_MONTHLY_CREDITS)
            bp.refresh_from_db()

        return Response({
            "email": request.user.email,
            "plan": bp.plan,
            "free_monthly_credits": bp.free_monthly_credits,
            "prepaid_credits": bp.prepaid_credits,
            "credits_used_total": bp.credits_used_total,
            "current_period_end": bp.current_period_end.isoformat() if bp.current_period_end else None,
            "cancel_at_period_end": bp.cancel_at_period_end,
        })

# (mantém seus imports/constantes/helpers já existentes no arquivo)
# - NETWORKLINK_HREF_RE
# - DEFAULT_ALLOWED_HOST_SUFFIXES, etc
# - _debug_enabled, _save_kml_debug_bundle_storage
# - NetworkLinkResolveError
# - e todos os helpers _resolve_networklink_if_needed, _findall_anyns, etc (já estão na sua classe)


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

    # ---------- helpers namespace-agnostic ----------

    def _coords_latlon_to_geojson_ring(self, coords_latlon):
        ring = []
        for p in coords_latlon or []:
            try:
                ring.append([float(p["longitude"]), float(p["latitude"])])
            except Exception:
                continue
        if len(ring) >= 3 and ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring

    def _kml_str_to_geojson(self, kml_str: str) -> dict:
        if not kml_str:
            return {"type": "FeatureCollection", "features": []}

        try:
            root = ET.fromstring(kml_str.encode("utf-8", errors="ignore"))
        except Exception:
            return {"type": "FeatureCollection", "features": []}

        features = []
        poly_idx = 0

        placemarks = list(self._findall_anyns(root, "Placemark"))
        if not placemarks:
            placemarks = [root]

        for placemark in placemarks:
            name_el = self._first_anyns(placemark, "name")
            base_name = (name_el.text or "").strip() if name_el is not None else ""

            for poly in self._findall_anyns(placemark, "Polygon"):
                outer = self._first_anyns(poly, "outerBoundaryIs")
                if outer is None:
                    continue

                lr = self._first_anyns(outer, "LinearRing")
                if lr is None:
                    continue

                coord_el = self._first_anyns(lr, "coordinates")
                if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                    continue

                coords_latlon = self._parse_kml_coordinates_text(coord_el.text)
                ring = self._coords_latlon_to_geojson_ring(coords_latlon)
                if len(ring) < 4:
                    continue

                poly_idx += 1
                fname = base_name or f"Polygon {poly_idx}"

                features.append(
                    {
                        "type": "Feature",
                        "properties": {"name": fname, "idx": poly_idx},
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    }
                )

        return {"type": "FeatureCollection", "features": features}

    def _parcelas_to_geojson(self, parcelas):
        features = []
        idx = 0

        for p in parcelas:
            ring = []
            for c in p.get("coords", []):
                try:
                    ring.append([float(c["longitude"]), float(c["latitude"])])
                except Exception:
                    continue

            if len(ring) < 3:
                continue

            if ring[0] != ring[-1]:
                ring.append(ring[0])

            idx += 1
            features.append(
                {
                    "type": "Feature",
                    "properties": {"name": p.get("talhao"), "idx": idx},
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                }
            )

        return {"type": "FeatureCollection", "features": features}

    def _findall_anyns(self, node, tag: str):
        for el in node.findall(f".//{{*}}{tag}"):
            yield el
        for el in node.findall(f".//{tag}"):
            yield el

    def _first_anyns(self, node, tag: str):
        for el in self._findall_anyns(node, tag):
            return el
        return None

    def _parse_kml_coordinates_text(self, text: str):
        coords = []
        if not text:
            return coords
        tokens = text.replace("\n", " ").replace("\t", " ").split()
        for token in tokens:
            parts = token.split(",")
            if len(parts) < 2:
                continue
            try:
                lon = float(parts[0])
                lat = float(parts[1])
            except ValueError:
                continue
            coords.append({"latitude": lat, "longitude": lon})
        return coords
    
        # -----------------------------
    # NetworkLink robust (como antes)
    # -----------------------------

    def _bytes_has_coordinates(self, b: bytes) -> bool:
        # FAST PATH: evita decodificar inteiro
        try:
            return b.lower().find(b"<coordinates") != -1
        except Exception:
            return False

    def _is_networklink_kml(self, text: str) -> bool:
        t = (text or "").lower()
        # NetworkLink típico: tem <NetworkLink><Link><href>... e não tem <coordinates>
        return ("<networklink" in t) and ("<href" in t) and ("<coordinates" not in t)

    def _extract_networklink_href(self, text: str):
        if not text:
            return None

        # 1) regex (rápido)
        m = NETWORKLINK_HREF_RE.search(text)
        if m:
            href = (m.group(1) or "").strip()
            return href or None

        # 2) fallback: XML parse e pega <href> namespace-agnostic
        try:
            root = ET.fromstring(text.encode("utf-8", errors="ignore"))

            href_el = None
            for el in root.findall(".//{*}href"):
                href_el = el
                break
            if href_el is None:
                for el in root.findall(".//href"):
                    href_el = el
                    break

            if href_el is None:
                return None

            href = "".join(href_el.itertext()).strip()
            return href or None
        except Exception:
            return None

    def _allowed_hosts(self):
        return getattr(
            settings,
            "KML_NETLINK_ALLOWED_HOST_SUFFIXES",
            DEFAULT_ALLOWED_HOST_SUFFIXES,
        )

    def _remote_limits(self):
        return {
            "max_bytes": getattr(settings, "KML_NETLINK_MAX_BYTES", DEFAULT_MAX_REMOTE_BYTES),
            "connect_timeout": getattr(settings, "KML_NETLINK_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT),
            "read_timeout": getattr(settings, "KML_NETLINK_READ_TIMEOUT", DEFAULT_READ_TIMEOUT),
            "max_redirects": getattr(settings, "KML_NETLINK_MAX_REDIRECTS", DEFAULT_MAX_REDIRECTS),
            "ttl": getattr(settings, "KML_NETLINK_CACHE_TTL", DEFAULT_CACHE_TTL_SECONDS),
        }

    def _is_allowed_host(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        host = host.lower().strip()
        allowed = self._allowed_hosts()
        return any(host == s or host.endswith("." + s) for s in allowed)

    def _fetch_remote(self, url: str) -> bytes:
        if not self._is_allowed_host(url):
            raise NetworkLinkResolveError(f"Host não permitido: {urlparse(url).hostname}")

        lim = self._remote_limits()
        cache_key = f"netlink:v2:{url}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            with requests.Session() as s:
                s.max_redirects = lim["max_redirects"]
                r = s.get(
                    url,
                    timeout=(lim["connect_timeout"], lim["read_timeout"]),
                    stream=True,
                    headers={"User-Agent": "kmlunifier/1.0"},
                )
                r.raise_for_status()

                cl = r.headers.get("Content-Length")
                if cl and int(cl) > lim["max_bytes"]:
                    raise NetworkLinkResolveError("Arquivo remoto excede o limite de tamanho.")

                chunks = []
                total = 0
                for chunk in r.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > lim["max_bytes"]:
                        raise NetworkLinkResolveError("Arquivo remoto excede o limite de tamanho.")
                    chunks.append(chunk)

                data = b"".join(chunks)

        except requests.exceptions.Timeout:
            raise NetworkLinkResolveError("Timeout ao resolver NetworkLink.")
        except requests.exceptions.TooManyRedirects:
            raise NetworkLinkResolveError("Redirects demais ao resolver NetworkLink.")
        except requests.RequestException as e:
            raise NetworkLinkResolveError(f"Falha HTTP ao resolver NetworkLink: {e}")

        cache.set(cache_key, data, lim["ttl"])
        return data

    def _maybe_extract_kml_from_kmz(self, data: bytes) -> bytes:
        # Verifica o "Magic Number" do ZIP (PK..)
        if not data or len(data) < 4 or data[:2] != b"PK":
            return data

        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                names = zf.namelist()
                
                # Prioridade 1: Arquivo padrão doc.kml
                if "doc.kml" in names:
                    return zf.read("doc.kml")
                
                # Prioridade 2: Qualquer arquivo que termine com .kml
                for n in names:
                    if n.lower().endswith(".kml"):
                        return zf.read(n)
            return data
        except Exception as e:
            print(f"Erro ao extrair KMZ: {e}")
            return data

    def _resolve_networklink_if_needed(self, raw_bytes: bytes, filename: str):
        """
        Retorna: (bytes_resolvidos, info_dict)
        info_dict: {networklink_detected, networklink_resolved, networklink_href, networklink_error}
        """
        info = {
            "networklink_detected": False,
            "networklink_resolved": False,
            "networklink_href": None,
            "networklink_error": None,
        }

        # FAST PATH: se já tem coordinates, não faz nada
        if self._bytes_has_coordinates(raw_bytes):
            return raw_bytes, info

        # Só agora decodifica
        try:
            text = raw_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

        if not self._is_networklink_kml(text):
            return raw_bytes, info

        info["networklink_detected"] = True
        href = self._extract_networklink_href(text)
        info["networklink_href"] = href

        if not href:
            info["networklink_error"] = "NetworkLink sem href."
            return raw_bytes, info

        try:
            remote = self._fetch_remote(href)
            remote = self._maybe_extract_kml_from_kmz(remote)

            if not self._bytes_has_coordinates(remote):
                info["networklink_error"] = "Conteúdo remoto não contém <coordinates>."
                return raw_bytes, info

            info["networklink_resolved"] = True
            return remote, info

        except Exception as e:
            info["networklink_error"] = str(e)
            return raw_bytes, info
    
    def _safe_filename(name: str) -> str:
        name = (name or "").strip()
        if not name:
            return "input.kml"
        # mantém extensão se existir
        base = os.path.basename(name)
        return base.replace("..", ".")


    # ----------------------------------------------------------
    # ✅ IMPORTANTE: os helpers de NetworkLink (resolve, fetch, etc)
    # permanecem na sua classe como já estão no seu arquivo.
    # Aqui nós apenas chamamos: self._resolve_networklink_if_needed(...)
    # ----------------------------------------------------------

    def post(self, request, *args, **kwargs):
        week_key = None
        weekly_used = None
        request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        files = request.FILES.getlist("files")
        mode = request.data.get("merge_mode", "union")
        print('[MODE] - ', mode)
        if not files:
            return Response(
                {"detail": "Nenhum arquivo enviado. Use o campo 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bp = getattr(request.user, "billing", None)
        if not bp:
            return Response(
                {
                    "detail": "BillingProfile ausente. Faça login novamente.",
                    "code": "BILLING_PROFILE_MISSING",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Semana (analytics)
        today = timezone.localdate()
        year, week_num, _ = today.isocalendar()
        week_key = f"{year}{week_num:02d}"

        debug_enabled = False
        try:
            debug_enabled = _debug_enabled()
        except Exception:
            debug_enabled = False

        # tol_m
        try:
            tol_m = float(request.data.get("tol_m", 20.0))
            print("[TOL_M] tol_m received from FrontEnd:", tol_m)
        except (TypeError, ValueError):
            tol_m = 20.0
        tol_m = self.clamp(tol_m, min_value=1.0)

        # corridor_width_m
        try:
            corridor_width_m = float(request.data.get("corridor_width_m", 1.0))
            print("[corridor_width_m] received from FrontEnd:", corridor_width_m)
        except (TypeError, ValueError):
            corridor_width_m = 1.0
        corridor_width_m = self.clamp(corridor_width_m, min_value=1.0)

        parcelas = []
        total_polygons = 0
        debug_files = []
        file_reports = []
        input_storage_paths = []  # paths dos inputs persistidos

        try:
            # -----------------------
            # Processar cada input
            # -----------------------
            for idx, uploaded in enumerate(files, start=1):
                raw_bytes = uploaded.read()
                
                raw_bytes = self._maybe_extract_kml_from_kmz(raw_bytes)
                
                try:
                    # Se o arquivo original era .kmz, trocamos para .kml no nome salvo, 
                    # já que extraímos o conteúdo.
                    original_name = uploaded.name
                    if original_name.lower().endswith(".kmz"):
                        safe_name = os.path.splitext(original_name)[0] + ".kml"
                    else:
                        safe_name = self._safe_filename(original_name)
                except Exception:
                    safe_name = f"input_{idx}.kml"

                print("\n" + "=" * 60)
                print("arquivo recebido Nº:", idx)
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

                # --- NetworkLink support ---
                try:
                    resolved_bytes, netinfo = self._resolve_networklink_if_needed(raw_bytes, uploaded.name)
                except Exception as e:
                    resolved_bytes, netinfo = raw_bytes, {
                        "networklink_detected": True,
                        "networklink_resolved": False,
                        "networklink_href": None,
                        "networklink_error": f"resolver_crash: {type(e).__name__}: {e}",
                    }

                if netinfo.get("networklink_detected"):
                    print(
                        f"[NETLINK] detected={netinfo.get('networklink_detected')} "
                        f"resolved={netinfo.get('networklink_resolved')} "
                        f"href={netinfo.get('networklink_href')}"
                    )
                    if netinfo.get("networklink_error"):
                        print(f"[NETLINK] error={netinfo.get('networklink_error')}")

                # -----------------------
                # Persistir input resolvido no storage
                # -----------------------
                try:
                    safe_name = self._safe_filename(uploaded.name)  # você precisa ter esse helper definido na classe
                except Exception:
                    safe_name = os.path.basename(uploaded.name) or f"input_{idx}.kml"

                input_path = f"kml_unions/{request_id}/inputs/{idx:02d}_{safe_name}"
                try:
                    default_storage.save(input_path, ContentFile(resolved_bytes))
                    input_storage_paths.append(input_path)
                except Exception as e:
                    print(f"[INPUT_SAVE] Falha ao salvar input {uploaded.name}: {e}")

                # -----------------------
                # Extrair polígonos
                # -----------------------
                poly_idx_file = 0
                try:
                    root = ET.fromstring(resolved_bytes)

                    placemarks = list(self._findall_anyns(root, "Placemark"))
                    if not placemarks:
                        placemarks = [root]

                    for placemark in placemarks:
                        name_el = self._first_anyns(placemark, "name")
                        talhao_name_base = (name_el.text or "").strip() if name_el is not None else ""

                        if not talhao_name_base:
                            talhao_name_base = os.path.splitext(uploaded.name)[0]

                        poly_idx_pm = 0
                        for poly in self._findall_anyns(placemark, "Polygon"):
                            outer = self._first_anyns(poly, "outerBoundaryIs")
                            if outer is None:
                                continue

                            lr = self._first_anyns(outer, "LinearRing")
                            if lr is None:
                                continue

                            coord_el = self._first_anyns(lr, "coordinates")
                            if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                                continue

                            coords = self._parse_kml_coordinates_text(coord_el.text)
                            if len(coords) < 3:
                                continue

                            poly_idx_pm += 1
                            poly_idx_file += 1
                            total_polygons += 1

                            talhao_name = talhao_name_base if poly_idx_pm == 1 else f"{talhao_name_base}_{poly_idx_pm}"
                            parcelas.append({"talhao": talhao_name, "coords": coords})

                    print(f"✅ Polígonos extraídos desse arquivo: {poly_idx_file}")

                    file_reports.append(
                        {
                            "filename": uploaded.name,
                            "polygons_extracted": poly_idx_file,
                            **netinfo,
                        }
                    )

                except ET.ParseError as e:
                    print(f"❌ Erro de parse XML em {uploaded.name}: {e}")
                    file_reports.append(
                        {
                            "filename": uploaded.name,
                            "polygons_extracted": 0,
                            **netinfo,
                            "parse_error": str(e),
                        }
                    )
                except Exception as e:
                    print(f"❌ Erro ao processar KML {uploaded.name}: {e}")
                    file_reports.append(
                        {
                            "filename": uploaded.name,
                            "polygons_extracted": 0,
                            **netinfo,
                            "process_error": str(e),
                        }
                    )

            print("=" * 60)
            print(f"📊 Total de polígonos extraídos de todos os arquivos: {total_polygons}")
            print(f"📊 Total de parcelas geradas: {len(parcelas)}")
            print("=" * 60)

            if not parcelas:
                return Response(
                    {
                        "detail": "Nenhum polígono válido encontrado nos arquivos KML.",
                        "request_id": request_id,
                        "files_report": file_reports,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ## -----------------------
            # Merge
            # -----------------------
            try:
                merge_mode = (mode or "union").lower().strip()
                print("[MERGE HERE MODE] -", merge_mode)

                debug_geojson = None

                if merge_mode == "no_union":
                    kml_str, metrics, debug_geojson = merge_no_flood_not_union(
                        parcelas,
                        tol_m=tol_m,
                        corridor_width_m=corridor_width_m,
                        return_metrics=True,
                    )
                else:
                    kml_str, metrics = merge_no_flood(
                        parcelas,
                        tol_m=tol_m,
                        corridor_width_m=corridor_width_m,
                        return_metrics=True,
                    )

                print("[KML_OUT] snippet:", (kml_str or "")[:500])

                # ✅ gera preview 1 vez
                preview_geojson = self._kml_str_to_geojson(kml_str)

                # ✅ injeta as linhas se existirem
                if debug_geojson:
                    extra_feats = (debug_geojson.get("features") or [])
                    if extra_feats:
                        preview_geojson["features"] = (preview_geojson.get("features") or []) + extra_feats

                print("[PREVIEW] geojson features:", len(preview_geojson.get("features", [])))

                input_preview_geojson = self._parcelas_to_geojson(parcelas)

            except Exception as e:
                print(f"❌ Erro interno no merge_no_flood: {e}")
                return Response(
                    {
                        "detail": "Erro interno ao unificar polígonos.",
                        "request_id": request_id,
                        "files_report": file_reports,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # -----------------------
            # Salvar output
            # -----------------------
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"kml_unions/union_{ts}_{uuid.uuid4().hex[:6]}.kml"
            saved_path = default_storage.save(filename, ContentFile((kml_str or "").encode("utf-8")))

            # URL (fallback)
            try:
                download_url = default_storage.url(saved_path)
            except NotImplementedError:
                media_url = settings.MEDIA_URL
                if not media_url.endswith("/"):
                    media_url += "/"
                download_url = request.build_absolute_uri(media_url + saved_path)
            except Exception:
                download_url = None

            # -----------------------
            # Analytics: WeeklyUsage
            # -----------------------
            with transaction.atomic():
                try:
                    usage, _ = WeeklyUsage.objects.select_for_update().get_or_create(
                        user=request.user,
                        week=week_key,
                        defaults={"count": 0},
                    )
                except IntegrityError:
                    usage = WeeklyUsage.objects.select_for_update().get(user=request.user, week=week_key)

                usage.count += 1
                usage.save(update_fields=["count", "updated_at"])
                weekly_used = usage.count

            # -----------------------
            # Persistir Job + Meta
            # -----------------------
            job = None
            try:
                import json  # garante import aqui
                input_filenames = [getattr(f, "name", "") for f in files]
                plan_now = getattr(request.user.billing, "plan", None)

                meta = {
                    "request_id": request_id,
                    "user_email": getattr(request.user, "email", None),
                    "created_at": timezone.now().isoformat(),
                    "tol_m": tol_m,
                    "corridor_width_m": corridor_width_m,
                    "total_files": len(files),
                    "total_polygons": total_polygons,
                    "metrics": metrics or {},
                    "files_report": file_reports or [],
                    "input_filenames": input_filenames,
                    "input_storage_paths": input_storage_paths,
                    "output_storage_path": saved_path,
                }

                meta_path = f"kml_unions/{request_id}/meta/meta.json"
                default_storage.save(
                    meta_path,
                    ContentFile(json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")),
                )

                job = KMLMergeJob.objects.create(
                    user=request.user,
                    request_id=request_id,
                    plan=(plan_now or getattr(bp, "plan", "unknown") or "unknown"),
                    status=KMLMergeJob.STATUS_SUCCESS,
                    tol_m=tol_m,
                    corridor_width_m=corridor_width_m,
                    total_files=len(files),
                    total_polygons=total_polygons,
                    output_polygons=(metrics or {}).get("output_polygons"),
                    merged_polygons=(metrics or {}).get("merged_polygons"),
                    input_area_m2=(metrics or {}).get("input_area_m2"),
                    input_area_ha=(metrics or {}).get("input_area_ha"),
                    output_area_m2=(metrics or {}).get("output_area_m2"),
                    output_area_ha=(metrics or {}).get("output_area_ha"),
                    storage_path=saved_path,
                    metrics=metrics or {},
                    input_filenames=input_filenames,
                    input_storage_paths=input_storage_paths,
                    meta_storage_path=meta_path,
                )
            except Exception as e:
                print(f"[KML_HISTORY] Falha ao salvar histórico do merge {request_id}: {e}")

            # -----------------------
            # Debug bundle (opcional)
            # -----------------------
            if debug_enabled:
                try:
                    Thread(
                        target=_save_kml_debug_bundle_storage,
                        args=(request_id, tol_m, corridor_width_m, debug_files, kml_str, metrics),
                        daemon=True,
                    ).start()
                except Exception:
                    pass

            # -----------------------
            # Resposta / gating
            # -----------------------
            try:
                bp.refresh_from_db()
            except Exception:
                pass

            plan = (getattr(bp, "plan", None) or "free").lower().strip()
            prepaid_left = int(getattr(bp, "prepaid_credits", 0) or 0)
            free_left = int(getattr(bp, "free_monthly_credits", 0) or 0)
            credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0)

            is_unlimited = bool(getattr(bp, "is_unlimited", False)) or plan in ("pro_monthly", "pro_yearly")

            download_available = bool(is_unlimited) or prepaid_left > 0
            download_url_out = download_url if download_available else None

            return Response(
                {
                    "request_id": request_id,
                    "job_id": str(job.id) if job else None,
                    "download_available": download_available,
                    "download_url": download_url_out,  # null para free

                    "total_polygons": total_polygons,
                    "total_files": len(files),
                    "tol_m": tol_m,
                    "corridor_width_m": corridor_width_m,
                    "output_polygons": (metrics or {}).get("output_polygons"),
                    "merged_polygons": (metrics or {}).get("merged_polygons"),
                    "input_area_m2": (metrics or {}).get("input_area_m2"),
                    "input_area_ha": (metrics or {}).get("input_area_ha"),
                    "output_area_m2": (metrics or {}).get("output_area_m2"),
                    "output_area_ha": (metrics or {}).get("output_area_ha"),

                    "plan": plan,
                    "week": week_key,
                    "weekly_used": weekly_used,
                    "free_monthly_credits": free_left,
                    "prepaid_credits": prepaid_left,
                    "credits_used_total": credits_used_total,

                    "files_report": file_reports,
                    "input_preview_geojson": input_preview_geojson,
                    "preview_geojson": preview_geojson,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"detail": str(e) or "Merge failed.", "code": "MERGE_FAILED"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class KMLDownloadView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        job = get_object_or_404(KMLMergeJob, id=job_id, user=request.user)

        bp = getattr(request.user, "billing", None)
        if not bp:
            return Response(
                {"detail": "BillingProfile ausente.", "code": "BILLING_PROFILE_MISSING"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        plan = (getattr(bp, "plan", None) or "free").lower().strip()
        is_unlimited = bool(getattr(bp, "is_unlimited", False)) or plan in ("pro_monthly", "pro_yearly")

        consumed = False
        prepaid_after = None

        # ✅ Pro/unlimited: sempre ok (não consome)
        if not is_unlimited:
            # ✅ Prepaid: consome 1 crédito agora (atomic)
            with transaction.atomic():
                bp = BillingProfile.objects.select_for_update().get(pk=bp.pk)

                prepaid_left = int(getattr(bp, "prepaid_credits", 0) or 0)
                if prepaid_left <= 0:
                    return Response(
                        {
                            "detail": "No credits left. Please buy prepaid credits or go Pro.",
                            "code": "NO_CREDITS_LEFT",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                bp.prepaid_credits = prepaid_left - 1
                bp.credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0) + 1
                bp.save(update_fields=["prepaid_credits", "credits_used_total", "updated_at"])

                consumed = True
                prepaid_after = int(bp.prepaid_credits or 0)

        # ✅ Mantém comportamento: retorna URL
        try:
            url = default_storage.url(job.storage_path)
        except Exception:
            url = None

        if not url:
            return Response(
                {"detail": "Could not generate download URL.", "code": "DOWNLOAD_URL_FAILED"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ✅ Enfileira envio do e-mail (não trava o request)
        to_email = getattr(request.user, "email", None)
        email_queued = False

        # Só enfileira se os artefatos existirem (evita thread inútil)
        has_inputs = bool(getattr(job, "input_storage_paths", None))
        has_meta = bool(getattr(job, "meta_storage_path", None))
        has_output = bool(getattr(job, "storage_path", None))

        if to_email and has_inputs and has_meta and has_output:
            queue_job_zip_email(job_id=str(job.id), to_email=to_email, plan=plan)
            email_queued = True

        payload = {
            "download_url": url,
            "consumed": consumed,
            "plan": plan,
            "email_queued": email_queued,
            "sent_to": to_email if email_queued else None,
        }

        if prepaid_after is not None:
            payload["prepaid_credits"] = prepaid_after

        return Response(payload, status=status.HTTP_200_OK)

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

        bp = getattr(request.user, "billing", None)
        if not bp:
            return Response(
                {
                    "plan": "free",
                    "week": week_key,
                    "weekly_used": used,
                    "free_monthly_credits": 0,
                    "prepaid_credits": 0,
                    "credits_used_total": 0,
                    "is_unlimited": False,
                    "current_period_end": None,
                    "cancel_at_period_end": False,
                },
                status=status.HTTP_200_OK,
            )

        # UX: se free, reseta mensal ao consultar
        if bp.plan == "free":
            bp.reset_free_monthly_if_needed(monthly_amount=FREE_MONTHLY_CREDITS)
            bp.refresh_from_db()

        return Response(
            {
                "plan": bp.plan,
                "week": week_key,
                "weekly_used": used,
                "free_monthly_credits": bp.free_monthly_credits,
                "prepaid_credits": bp.prepaid_credits,
                "credits_used_total": bp.credits_used_total,
                "is_unlimited": bp.is_unlimited,
                "current_period_end": bp.current_period_end.isoformat() if bp.current_period_end else None,
                "cancel_at_period_end": bp.cancel_at_period_end,
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

        price_id = (
            os.getenv("STRIPE_PRICE_ID_MONTHLY")
            if billing_cycle == "monthly"
            else os.getenv("STRIPE_PRICE_ID_YEARLY")
        )
        if not price_id:
            return Response(
                {"detail": "Stripe price_id não configurado no servidor.", "code": "STRIPE_PRICE_ID_MISSING"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        app_url = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
        success_url = f"{app_url}/?stripe=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{app_url}/?stripe=cancel"

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

# kmltools/views.py (ou onde você mantém o webhook)
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


def _extract_firebase_uid(obj: dict):
    """
    Tenta extrair firebase_uid de onde normalmente aparece:
    - obj.metadata.firebase_uid / user_uid / uid
    - subscription.customer.metadata (não vem no evento; só via retrieve/expand)
    - checkout.session.client_reference_id (se você setar como firebase_uid)
    """
    if not isinstance(obj, dict):
        return None

    # 1) metadata direto no objeto do evento
    md = obj.get("metadata") or {}
    for k in ("firebase_uid", "user_uid", "uid"):
        v = md.get(k)
        if v:
            return str(v)

    # 2) checkout.session: client_reference_id
    cr = obj.get("client_reference_id")
    if cr:
        return str(cr)

    return None


def _find_bp(customer_id=None, firebase_uid=None):
    """
    No seu schema: BillingProfile.user e firebase_uid são obrigatórios.
    Então: webhook só atualiza BP existente.
    """
    bp = None
    if customer_id:
        bp = BillingProfile.objects.filter(stripe_customer_id=customer_id).first()
    if not bp and firebase_uid:
        bp = BillingProfile.objects.filter(firebase_uid=firebase_uid).first()
    return bp



def _sync_bp_from_subscription(bp: BillingProfile, sub: dict, period_end_fallback=None):
    status_ = (sub.get("status") or "").lower().strip()

    raw_cpe = sub.get("current_period_end")
    raw_cap = sub.get("cancel_at_period_end")
    raw_cancel_at = sub.get("cancel_at")

    cpe = _dt_from_unix(raw_cpe, "sub.current_period_end")
    cancel_at_dt = _dt_from_unix(raw_cancel_at, "sub.cancel_at")

    if not cpe and cancel_at_dt:
        cpe = cancel_at_dt
    if not cpe and period_end_fallback:
        cpe = period_end_fallback
    if not cpe:
        cpe = _derive_period_end_from_anchor(sub)

    cap_local = bool(raw_cap) or bool(cancel_at_dt)

    bp.stripe_subscription_id = sub.get("id") or bp.stripe_subscription_id
    bp.current_period_end = cpe
    bp.cancel_at_period_end = cap_local

    now = timezone.now()

    # intervalo: month/year
    interval = None
    try:
        items = (sub.get("items") or {}).get("data") or []
        if items:
            price = items[0].get("price") or {}
            recurring = price.get("recurring") or {}
            interval = (recurring.get("interval") or "").lower().strip()
    except Exception:
        interval = None

    if status_ in ("active", "trialing"):
        bp.plan = "pro_yearly" if interval == "year" else "pro_monthly"
    else:
        if cpe and cpe > now:
            # ainda dentro do período: mantém pro_* se já estava, senão assume monthly
            if bp.plan not in ("pro_monthly", "pro_yearly"):
                bp.plan = "pro_monthly"
        else:
            # rebaixa para free apenas se estava em pro_*
            if bp.plan in ("pro_monthly", "pro_yearly"):
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
        "[stripe][sync] saved -> bp_id:", bp.id,
        "plan:", bp.plan,
        "cpe:", bp.current_period_end,
        "cap(local):", bp.cancel_at_period_end,
        "status:", status_,
        "interval:", interval,
        "raw_cap:", raw_cap,
        "raw_cancel_at:", raw_cancel_at,
        "raw_cpe:", raw_cpe,
        "billing_cycle_anchor:", sub.get("billing_cycle_anchor"),
        "period_end_fallback:", period_end_fallback,
    )


def _retrieve_subscription(subscription_id: str):
    return stripe.Subscription.retrieve(subscription_id, expand=["items.data.price"])



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
            print("[stripe] missing STRIPE_WEBHOOK_SECRET")
            return HttpResponse(status=500)

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except Exception as e:
            print("[stripe] signature error:", str(e))
            return HttpResponse(status=400)

        event_type = event.get("type")
        obj = (event.get("data") or {}).get("object") or {}
        event_id = event.get("id")

        print("[stripe] event:", event_type, "id:", event_id)

        # 1) subscription created/updated
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            customer_id = obj.get("customer")
            sub_id = obj.get("id")
            firebase_uid = _extract_firebase_uid(obj)

            print("[stripe] sub event:", event_type, "customer:", customer_id, "sub:", sub_id, "firebase_uid:", firebase_uid)

            bp = _find_bp(customer_id=customer_id, firebase_uid=firebase_uid)
            if not bp:
                print("[stripe] BP NOT FOUND (sub). Will not create. customer:", customer_id, "firebase_uid:", firebase_uid)
                return HttpResponse(status=200)

            if customer_id and not bp.stripe_customer_id:
                bp.stripe_customer_id = customer_id
                bp.save(update_fields=["stripe_customer_id", "updated_at"])
                print("[stripe] set bp.stripe_customer_id from sub event -> bp_id:", bp.id, "customer:", customer_id)

            if sub_id:
                try:
                    sub = _retrieve_subscription(sub_id)
                    _sync_bp_from_subscription(bp, sub)
                except Exception as e:
                    print("[stripe] retrieve sub failed:", str(e))

            return HttpResponse(status=200)

        # 2) checkout.session.completed (subscription OR prepaid payment)
        if event_type == "checkout.session.completed":
            customer_id = obj.get("customer")
            subscription_id = obj.get("subscription")
            firebase_uid = _extract_firebase_uid(obj)

            mode = (obj.get("mode") or "").lower().strip()
            kind = ((obj.get("metadata") or {}).get("kind") or "").lower().strip()

            print(
                "[stripe] checkout completed customer:", customer_id,
                "mode:", mode,
                "kind:", kind,
                "sub:", subscription_id,
                "firebase_uid:", firebase_uid
            )

            bp = _find_bp(customer_id=customer_id, firebase_uid=firebase_uid)
            if not bp:
                print("[stripe] BP NOT FOUND (checkout). Will not create. customer:", customer_id, "firebase_uid:", firebase_uid)
                return HttpResponse(status=200)

            if customer_id and (bp.stripe_customer_id != customer_id):
                bp.stripe_customer_id = customer_id
                bp.save(update_fields=["stripe_customer_id", "updated_at"])
                print("[stripe] updated bp.stripe_customer_id from checkout -> bp_id:", bp.id, "customer:", customer_id)

            # PREPAID
            if mode == "payment" and kind == "prepaid_10":
                with transaction.atomic():
                    bp = BillingProfile.objects.select_for_update().get(pk=bp.pk)
                    bp.prepaid_credits += PREPAID_CREDITS_PER_PACK
                    if not bp.is_unlimited:
                        bp.plan = "prepaid"
                    bp.save(update_fields=["prepaid_credits", "plan", "updated_at"])
                return HttpResponse(status=200)

            # SUBSCRIPTION
            if subscription_id:
                bp.stripe_subscription_id = subscription_id
                bp.save(update_fields=["stripe_subscription_id", "updated_at"])

                try:
                    sub = _retrieve_subscription(subscription_id)
                    _sync_bp_from_subscription(bp, sub)
                except Exception as e:
                    print("[stripe] checkout retrieve/sync failed:", str(e))

            return HttpResponse(status=200)

        # 3) invoice events (fallback)
        if event_type in ("invoice.paid", "invoice.payment_succeeded"):
            invoice = obj
            customer_id = invoice.get("customer")
            subscription_id = invoice.get("subscription")
            firebase_uid = _extract_firebase_uid(invoice)

            print("[stripe] invoice event:", event_type, "customer:", customer_id, "sub:", subscription_id, "firebase_uid:", firebase_uid)

            cpe_from_invoice = _extract_period_end_from_invoice(invoice)
            print("[stripe] cpe from invoice:", cpe_from_invoice)

            bp = _find_bp(customer_id=customer_id, firebase_uid=firebase_uid)
            if not bp:
                print("[stripe] BP NOT FOUND (invoice). Will not create. customer:", customer_id, "firebase_uid:", firebase_uid)
                return HttpResponse(status=200)

            if customer_id and (bp.stripe_customer_id != customer_id):
                bp.stripe_customer_id = customer_id
                bp.save(update_fields=["stripe_customer_id", "updated_at"])
                print("[stripe] updated bp.stripe_customer_id from invoice -> bp_id:", bp.id, "customer:", customer_id)

            if subscription_id:
                try:
                    sub = _retrieve_subscription(subscription_id)
                    _sync_bp_from_subscription(bp, sub, period_end_fallback=cpe_from_invoice)
                except Exception as e:
                    print("[stripe] invoice retrieve sub failed:", str(e))
                    if cpe_from_invoice:
                        # fallback mínimo: mantém pro_* se já estava; senão assume monthly
                        if bp.plan not in ("pro_monthly", "pro_yearly"):
                            bp.plan = "pro_monthly"
                        bp.stripe_subscription_id = subscription_id
                        bp.current_period_end = cpe_from_invoice
                        bp.save(update_fields=["plan", "stripe_subscription_id", "current_period_end", "updated_at"])
                        print("[stripe] saved cpe from invoice only -> bp_id:", bp.id)

            return HttpResponse(status=200)

        # 4) subscription deleted
        if event_type == "customer.subscription.deleted":
            customer_id = obj.get("customer")
            firebase_uid = _extract_firebase_uid(obj)

            print("[stripe] subscription deleted customer:", customer_id, "firebase_uid:", firebase_uid)

            bp = _find_bp(customer_id=customer_id, firebase_uid=firebase_uid)
            if not bp:
                print("[stripe] BP NOT FOUND (deleted). Will not create. customer:", customer_id, "firebase_uid:", firebase_uid)
                return HttpResponse(status=200)

            # só rebaixa para free se estava em pro_*
            if bp.plan in ("pro_monthly", "pro_yearly"):
                bp.plan = "free"

            bp.current_period_end = None
            bp.stripe_subscription_id = None
            bp.cancel_at_period_end = False
            bp.save(update_fields=["plan", "current_period_end", "stripe_subscription_id", "cancel_at_period_end", "updated_at"])
            print("[stripe] subscription deleted -> bp_id:", bp.id, "new_plan:", bp.plan)

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



class CreatePrepaidCheckoutSessionView(APIView):
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

        price_id = os.getenv("STRIPE_PRICE_ID_PREPAID_10")
        if not price_id:
            return Response(
                {"detail": "Stripe price_id prepaid não configurado.", "code": "STRIPE_PRICE_ID_MISSING"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        app_url = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
        success_url = f"{app_url}/?stripe=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{app_url}/?stripe=cancel"

        if not bp.stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email,
                metadata={"firebase_uid": bp.firebase_uid, "django_user_id": str(request.user.id)},
            )
            bp.stripe_customer_id = customer["id"]
            bp.save(update_fields=["stripe_customer_id", "updated_at"])

        session = stripe.checkout.Session.create(
            mode="payment",
            customer=bp.stripe_customer_id,
            client_reference_id=str(request.user.id),
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "kind": "prepaid_10",
                "firebase_uid": bp.firebase_uid,
                "django_user_id": str(request.user.id),
            },
        )

        return Response({"checkout_url": session["url"], "session_id": session["id"]}, status=status.HTTP_200_OK)





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
