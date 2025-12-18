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

from .services import merge_no_flood


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

    def clamp(self, value, min_value=None, max_value=None):
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"detail": "Nenhum arquivo enviado. Use o campo 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            },
            status=status.HTTP_200_OK,
        )
