import os
import uuid
import xml.etree.ElementTree as ET

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

from .services import merge_no_flood
from datetime import datetime


class KMLUnionView(APIView):
    """
    POST /kmltools/kml-union/

    FormData:
      files: <file1.kml>
      files: <file2.kml>
      tol_m: 20              (opcional)
      corridor_width_m: 0.1  (opcional)

    Resposta:
    {
      "download_url": "https://seu-dominio.com/media/kml_unions/union_xxx.kml",
      "total_polygons": N,
      "total_files": M,
      "tol_m": 20.0,
      "corridor_width_m": 0.1
    }
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"detail": "Nenhum arquivo enviado. Use o campo 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # parâmetros opcionais
        try:
            tol_m = float(request.data.get("tol_m", 20.0))
        except (TypeError, ValueError):
            tol_m = 20.0

        try:
            corridor_width_m = float(request.data.get("corridor_width_m", 0.1))
        except (TypeError, ValueError):
            corridor_width_m = 0.1

        parcelas = []
        total_polygons = 0

        # namespace padrão do KML 2.2
        KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

        for uploaded in files:
            raw_bytes = uploaded.read()

            print("\n" + "=" * 60)
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

            try:
                # faz o parse XML
                root = ET.fromstring(raw_bytes)

                # percorre todos os Placemark
                for placemark in root.findall(".//kml:Placemark", KML_NS):
                    # nome do talhão (se tiver)
                    name_el = placemark.find("kml:name", KML_NS)
                    talhao_name_base = (
                        name_el.text.strip()
                        if name_el is not None and name_el.text
                        else ""
                    )

                    # se por algum motivo não tiver name, usamos nome do arquivo
                    if not talhao_name_base:
                        talhao_name_base = os.path.splitext(uploaded.name)[0]

                    poly_idx = 0

                    # para cada Polygon dentro do Placemark
                    for poly in placemark.findall(".//kml:Polygon", KML_NS):
                        coord_el = poly.find(
                            ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
                            KML_NS,
                        )
                        if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                            continue

                        coord_text = coord_el.text.strip()
                        # separa por espaço (cada token é "lon,lat" ou "lon,lat,alt")
                        coord_tokens = coord_text.split()

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

                            coords.append(
                                {
                                    "latitude": lat,
                                    "longitude": lon,
                                }
                            )

                        if not coords:
                            continue

                        poly_idx += 1
                        total_polygons += 1

                        # se tiver mais de um polígono dentro do mesmo Placemark,
                        # diferenciamos com sufixo _1, _2, etc.
                        talhao_name = (
                            talhao_name_base
                            if poly_idx == 1
                            else f"{talhao_name_base}_{poly_idx}"
                        )

                        parcelas.append(
                            {
                                "talhao": talhao_name,
                                "coords": coords,
                            }
                        )

                print(f"✅ Polígonos extraídos desse arquivo: {poly_idx}")

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
                {"detail": "Nenhum polígono válido encontrado nos arquivos KML."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- chama o merge_no_flood (teu core já de produção) ---
        try:
            kml_str, metrics = merge_no_flood(
                parcelas,
                tol_m=tol_m,
                corridor_width_m=corridor_width_m,
                return_metrics=True,
            )
        except ValueError as e:
            # ex.: "Nenhuma parcela válida recebida."
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"❌ Erro interno no merge_no_flood: {e}")
            return Response(
                {"detail": "Erro interno ao unificar polígonos."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # --- salva o KML em MEDIA_ROOT e devolve uma URL ---
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kml_unions/union_{ts}_{uuid.uuid4().hex[:6]}.kml"
        saved_path = default_storage.save(
            filename,
            ContentFile(kml_str.encode("utf-8")),
        )

        try:
            download_url = default_storage.url(saved_path)
        except NotImplementedError:
            # fallback para caso esteja usando FileSystemStorage em dev
            media_url = settings.MEDIA_URL
            if not media_url.endswith("/"):
                media_url += "/"
            download_url = request.build_absolute_uri(media_url + saved_path)

        return Response(
            {
                "download_url": download_url,
                "total_polygons": total_polygons,             # entrada (já existia)
                "output_polygons": metrics["merged_polygons"],  # saída

                "input_area_m2": metrics["input_area_m2"],
                "input_area_ha": metrics["input_area_ha"],
                "output_area_m2": metrics["output_area_m2"],
                "output_area_ha": metrics["output_area_ha"],
                
                "output_polygons": metrics["output_polygons"],
                "output_area_m2": metrics["output_area_m2"],   # em m²

                "total_files": len(files),
                "tol_m": tol_m,
                "corridor_width_m": corridor_width_m,
            },
            status=status.HTTP_200_OK,
        )