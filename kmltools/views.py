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
from .models import BillingProfile, WeeklyUsage, KMLMergeJob, UnlockFeedback
from kmltools.services import merge_no_flood, merge_no_flood_not_union
from kmltools.newservices.credits import reserve_one_credit, refund_one_credit, NoCreditsLeft


from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge, unary_union
import math

from django.utils.text import slugify
from .newservices.email_async import queue_job_zip_email
from rest_framework.permissions import AllowAny
import zipfile
from io import BytesIO
import re
import zipfile
from io import BytesIO
from urllib.parse import urlparse
import requests
from django.core.cache import cache
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from django.db.models import Q, Count , Sum
from rest_framework.exceptions import NotFound

import ipaddress

import logging
logger = logging.getLogger(__name__)


from django.http import JsonResponse
from django.views import View

from .emailer import send_reactivation_email


from threading import Thread
from django.db import close_old_connections

def start_kml_merge_thread(job_id):
    logger.warning("[ASYNC] on_commit fired for job_id=%s", job_id)
    t = Thread(target=run_kml_merge_job, args=(str(job_id),), daemon=True)
    t.start()
    logger.warning("[ASYNC] thread started for job_id=%s alive=%s", job_id, t.is_alive())

def _safe_storage_url(path):
    try:
        return default_storage.url(path) if path else None
    except Exception:
        return None

def build_concat_only_kml(file_entries):
    """
    file_entries = [
        {
            "filename": "...",
            "xml_bytes": b"..."
        }
    ]
    """
    view = KMLUnionView()

    document_parts = []
    preview_features = []
    total_polygons = 0
    total_markers = 0

    for idx, entry in enumerate(file_entries, start=1):
        filename = entry.get("filename") or f"file_{idx}.kml"
        xml_bytes = entry.get("xml_bytes") or b""

        try:
            root = view._safe_parse_xml(xml_bytes)
        except Exception:
            continue

        base_name = os.path.splitext(filename)[0] or f"File {idx}"

        # 1) tenta preservar folders inteiros
        folders = list(view._findall_anyns(root, "Folder"))
        if folders:
            for folder in folders:
                try:
                    xml_str = ET.tostring(folder, encoding="unicode")
                    if xml_str:
                        document_parts.append(xml_str)
                except Exception:
                    pass
        else:
            # 2) se não houver Folder, agrupa os placemarks num Folder por arquivo
            placemarks = list(view._findall_anyns(root, "Placemark"))
            if placemarks:
                folder_parts = [f"<Folder><name>{view._xml_escape(base_name)}</name>"]
                for pm in placemarks:
                    try:
                        xml_str = ET.tostring(pm, encoding="unicode")
                        if xml_str:
                            folder_parts.append(xml_str)
                    except Exception:
                        pass
                folder_parts.append("</Folder>")
                document_parts.append("\n".join(folder_parts))
            else:
                # 3) fallback: tenta pegar conteúdo do Document
                doc = view._first_anyns(root, "Document")
                if doc is not None:
                    try:
                        for child in list(doc):
                            xml_str = ET.tostring(child, encoding="unicode")
                            if xml_str:
                                document_parts.append(xml_str)
                    except Exception:
                        pass

        # preview polygons
        try:
            gj = view._kml_str_to_geojson(xml_bytes.decode("utf-8", errors="ignore"))
            feats = gj.get("features") or []
            preview_features.extend(feats)
            total_polygons += sum(
                1 for f in feats if (f.get("geometry") or {}).get("type") == "Polygon"
            )
        except Exception:
            pass

        # preview markers
        try:
            markers = view._extract_point_placemarks_as_geojson(root, fallback_name=base_name)
            preview_features.extend(markers)
            total_markers += len(markers)
        except Exception:
            pass

    kml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>KML Unifier — combined</name>
    {"".join(document_parts)}
  </Document>
</kml>'''

    preview_geojson = {
        "type": "FeatureCollection",
        "features": preview_features,
    }

    metrics = {
        "output_polygons": total_polygons,
        "merged_polygons": 0,
        "input_area_m2": 0,
        "input_area_ha": 0,
        "output_area_m2": 0,
        "output_area_ha": 0,
        "concat_only": True,
    }

    return (
        kml_str,
        metrics,
        preview_geojson,
        preview_geojson,
        total_polygons,
        total_markers,
    )
    
def _haversine_m(a, b):
    lon1, lat1 = a
    lon2, lat2 = b

    radius = 6371000.0

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    x = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    return 2 * radius * math.asin(math.sqrt(x))


def _line_length_m(line):
    coords = list(line.coords)
    total = 0.0

    for idx in range(1, len(coords)):
        total += _haversine_m(coords[idx - 1], coords[idx])

    return total


def _dedupe_consecutive_coords(coords):
    cleaned = []

    for pt in coords or []:
        if not cleaned or cleaned[-1] != pt:
            cleaned.append(pt)

    return cleaned


def _orient_coords_to_connect(base_end, candidate_coords):
    """
    Retorna candidate_coords na orientação que conecta melhor com base_end.
    """
    if not candidate_coords:
        return candidate_coords, None

    start = candidate_coords[0]
    end = candidate_coords[-1]

    dist_to_start = _haversine_m(base_end, start)
    dist_to_end = _haversine_m(base_end, end)

    if dist_to_start <= dist_to_end:
        return candidate_coords, dist_to_start

    return list(reversed(candidate_coords)), dist_to_end


def _build_line_components(lines, gap_m):
    """
    Monta componentes de linhas por proximidade de endpoints.
    Não usa unary_union, para evitar quebrar uma linha em dezenas/centenas de segmentos.
    """

    remaining = []

    for idx, item in enumerate(lines):
        coords = list(item["geom"].coords)
        if len(coords) < 2:
            continue

        remaining.append({
            "idx": idx,
            "name": item.get("name") or f"Line {idx + 1}",
            "coords": coords,
        })

    components = []
    bridge_reports = []
    bridges_created = 0

    gap_m = float(gap_m or 0)

    while remaining:
        current = remaining.pop(0)
        chain = list(current["coords"])
        chain_source_indexes = [current["idx"]]

        changed = True

        while changed and remaining:
            changed = False

            best = None

            chain_start = chain[0]
            chain_end = chain[-1]

            for pos, candidate in enumerate(remaining):
                cand_coords = candidate["coords"]
                cand_start = cand_coords[0]
                cand_end = cand_coords[-1]

                options = [
                    {
                        "pos": pos,
                        "attach": "end_to_start",
                        "distance_m": _haversine_m(chain_end, cand_start),
                        "coords": cand_coords,
                        "bridge_from": chain_end,
                        "bridge_to": cand_start,
                    },
                    {
                        "pos": pos,
                        "attach": "end_to_end",
                        "distance_m": _haversine_m(chain_end, cand_end),
                        "coords": list(reversed(cand_coords)),
                        "bridge_from": chain_end,
                        "bridge_to": cand_end,
                    },
                    {
                        "pos": pos,
                        "attach": "start_to_end",
                        "distance_m": _haversine_m(chain_start, cand_end),
                        "coords": cand_coords,
                        "bridge_from": cand_end,
                        "bridge_to": chain_start,
                    },
                    {
                        "pos": pos,
                        "attach": "start_to_start",
                        "distance_m": _haversine_m(chain_start, cand_start),
                        "coords": list(reversed(cand_coords)),
                        "bridge_from": cand_start,
                        "bridge_to": chain_start,
                    },
                ]

                for option in options:
                    if option["distance_m"] <= gap_m:
                        if best is None or option["distance_m"] < best["distance_m"]:
                            best = {
                                **option,
                                "candidate": candidate,
                            }

            if best is None:
                break

            candidate = best["candidate"]
            candidate_coords = best["coords"]
            dist_m = float(best["distance_m"])

            if best["attach"] in ("end_to_start", "end_to_end"):
                if dist_m > 0:
                    chain.append(best["bridge_to"])
                    bridges_created += 1

                    bridge_reports.append({
                        "from_line_index": chain_source_indexes[-1],
                        "to_line_index": candidate["idx"],
                        "attach": best["attach"],
                        "distance_m": round(dist_m, 2),
                    })

                chain.extend(candidate_coords)

            else:
                if dist_m > 0:
                    chain.insert(0, best["bridge_from"])
                    bridges_created += 1

                    bridge_reports.append({
                        "from_line_index": candidate["idx"],
                        "to_line_index": chain_source_indexes[0],
                        "attach": best["attach"],
                        "distance_m": round(dist_m, 2),
                    })

                chain = candidate_coords + chain

            chain = _dedupe_consecutive_coords(chain)
            chain_source_indexes.append(candidate["idx"])

            remaining.pop(best["pos"])
            changed = True

        chain = _dedupe_consecutive_coords(chain)

        if len(chain) >= 2:
            components.append({
                "coords": chain,
                "source_indexes": chain_source_indexes,
            })

    return components, bridges_created, bridge_reports


def build_line_merge_kml(parcelas, gap_m=20.0):
    """
    Usado somente quando os arquivos não têm Polygon e possuem LineString/LinearRing.

    Reaproveita o tol_m atual como gap_m:
    - conecta endpoints de linhas diferentes quando a distância entre eles <= gap_m
    - não cria área
    - não usa corridor_width_m
    - não usa unary_union, para não fragmentar a linha final
    """

    lines = []
    input_features = []

    for p in parcelas or []:
        talhao = p.get("talhao") or "Line"
        geoms = p.get("geoms") or []

        for geom in geoms:
            try:
                coords = list(geom.coords)
            except Exception:
                coords = []

            if len(coords) < 2:
                continue

            line = LineString(coords)

            lines.append({
                "name": talhao,
                "geom": line,
            })

            input_features.append({
                "type": "Feature",
                "properties": {
                    "name": talhao,
                    "kind": "input_line",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[float(x), float(y)] for x, y in coords],
                },
            })

    if not lines:
        raise ValueError("Nenhuma linha válida encontrada nos arquivos KML.")

    components, bridges_created, bridge_reports = _build_line_components(
        lines,
        gap_m=gap_m,
    )

    output_features = []
    output_lines = []

    for idx, component in enumerate(components, start=1):
        coords = component["coords"]

        if len(coords) < 2:
            continue

        line = LineString(coords)
        output_lines.append(line)

        output_features.append({
            "type": "Feature",
            "properties": {
                "name": f"Merged line {idx}",
                "kind": "merged_line",
                "idx": idx,
                "source_lines": component.get("source_indexes") or [],
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[float(x), float(y)] for x, y in coords],
            },
        })

    if not output_lines:
        raise ValueError("Não foi possível gerar linhas finais a partir dos arquivos KML.")

    kml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        '<name>KML Unifier — merged lines</name>',
        """
        <Style id="mergedLineStyle">
            <LineStyle>
                <color>ff00aaff</color>
                <width>4</width>
            </LineStyle>
        </Style>
        """,
    ]

    for idx, line in enumerate(output_lines, start=1):
        coord_text = " ".join(
            f"{float(x)},{float(y)},0"
            for x, y in line.coords
        )

        kml_parts.append(f"""
        <Placemark>
            <name>Merged line {idx}</name>
            <styleUrl>#mergedLineStyle</styleUrl>
            <LineString>
                <tessellate>1</tessellate>
                <coordinates>{coord_text}</coordinates>
            </LineString>
        </Placemark>
        """)

    kml_parts.extend([
        '</Document>',
        '</kml>',
    ])

    input_length_m = sum(_line_length_m(item["geom"]) for item in lines)
    output_length_m = sum(_line_length_m(line) for line in output_lines)

    preview_geojson = {
        "type": "FeatureCollection",
        "features": output_features,
    }

    input_preview_geojson = {
        "type": "FeatureCollection",
        "features": input_features,
    }

    metrics = {
        "geometry_type": "lines",
        "merge_mode": "line_merge",
        "gap_m": float(gap_m or 0),
        "input_lines": len(lines),
        "output_lines": len(output_lines),
        "bridges_created": bridges_created,
        "bridge_reports": bridge_reports,
        "input_length_m": round(float(input_length_m), 2),
        "input_length_km": round(float(input_length_m) / 1000, 3),
        "output_length_m": round(float(output_length_m), 2),
        "output_length_km": round(float(output_length_m) / 1000, 3),

        # compatibilidade com o restante do sistema
        "output_polygons": 0,
        "merged_polygons": 0,
        "input_area_m2": 0,
        "input_area_ha": 0,
        "output_area_m2": 0,
        "output_area_ha": 0,
    }

    return (
        "\n".join(kml_parts),
        metrics,
        preview_geojson,
        input_preview_geojson,
    )

    
def run_kml_merge_job(job_id):
    close_old_connections()
    logger.warning("[ASYNC] worker start job_id=%s", job_id)

    try:
        job = KMLMergeJob.objects.get(id=job_id)
        logger.warning("[ASYNC] job loaded job_id=%s status=%s total_files=%s", job_id, job.status, job.total_files)
    except KMLMergeJob.DoesNotExist:
        return

    try:
        job.status = getattr(KMLMergeJob, "STATUS_PROCESSING", "processing")
        job.save(update_fields=["status"])

        view = KMLUnionView()

        request_id = job.request_id
        tol_m = float(job.tol_m or 20.0)
        corridor_width_m = float(job.corridor_width_m or 0.0)

        parcelas = []
        total_polygons = 0
        file_reports = []
        markers = []
        total_cad_lines = 0

        input_storage_paths = list(job.input_storage_paths or [])
        input_filenames = list(job.input_filenames or [])
        
        resolved_file_entries = []
        
        logger.warning("[ASYNC] starting file loop job_id=%s files=%s", job_id, len(input_storage_paths))
        for idx, input_path in enumerate(input_storage_paths, start=1):
            with default_storage.open(input_path, "rb") as f:
                raw_bytes = f.read()

            safe_name = os.path.basename(input_path)
            raw_bytes = view._maybe_extract_kml_from_kmz(raw_bytes)

            try:
                resolved_bytes, netinfo = view._resolve_networklink_if_needed(raw_bytes, safe_name)
                resolved_file_entries.append({
                    "filename": input_filenames[idx - 1] if idx - 1 < len(input_filenames) else safe_name,
                    "xml_bytes": resolved_bytes,
                })
            except Exception as e:
                resolved_bytes, netinfo = raw_bytes, {
                    "networklink_detected": True,
                    "networklink_resolved": False,
                    "networklink_href": None,
                    "networklink_error": f"resolver_crash: {type(e).__name__}: {e}",
                }

            poly_idx_file = 0
            cad_lines_file = 0

            try:
                root = view._safe_parse_xml(resolved_bytes)

                try:
                    base_marker_name = os.path.splitext(safe_name)[0]
                    markers.extend(
                        view._extract_point_placemarks_as_geojson(
                            root,
                            fallback_name=base_marker_name,
                        )
                    )
                except Exception:
                    pass

                placemarks = list(view._findall_anyns(root, "Placemark"))
                if not placemarks:
                    placemarks = [root]

                for placemark in placemarks:
                    name_el = view._first_anyns(placemark, "name")
                    talhao_name_base = (name_el.text or "").strip() if name_el is not None else ""
                    if not talhao_name_base:
                        talhao_name_base = os.path.splitext(safe_name)[0]

                    has_poly = any(True for _ in view._findall_anyns(placemark, "Polygon"))
                    poly_idx_pm = 0

                    for poly in view._findall_anyns(placemark, "Polygon"):
                        outer = view._first_anyns(poly, "outerBoundaryIs")
                        if outer is None:
                            continue

                        lr = view._first_anyns(outer, "LinearRing")
                        if lr is None:
                            continue

                        coord_el = view._first_anyns(lr, "coordinates")
                        if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                            continue

                        coords = view._parse_kml_coordinates_text(coord_el.text)
                        if len(coords) < 3:
                            continue

                        poly_idx_pm += 1
                        poly_idx_file += 1
                        total_polygons += 1

                        talhao_name = talhao_name_base if poly_idx_pm == 1 else f"{talhao_name_base}_{poly_idx_pm}"
                        parcelas.append({"talhao": talhao_name, "coords": coords})

                    if not has_poly:
                        line_geoms = []

                        for ls in view._findall_anyns(placemark, "LineString"):
                            coord_el = view._first_anyns(ls, "coordinates")
                            if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                                continue

                            coords_ll = view._parse_kml_coordinates_text(coord_el.text)
                            if len(coords_ll) < 2:
                                continue

                            pts = [(float(p["longitude"]), float(p["latitude"])) for p in coords_ll]
                            if len(pts) >= 2:
                                line_geoms.append(LineString(pts))
                                cad_lines_file += 1

                        for lr in view._findall_anyns(placemark, "LinearRing"):
                            coord_el = view._first_anyns(lr, "coordinates")
                            if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                                continue

                            coords_ll = view._parse_kml_coordinates_text(coord_el.text)
                            if len(coords_ll) < 2:
                                continue

                            pts = [(float(p["longitude"]), float(p["latitude"])) for p in coords_ll]
                            if len(pts) >= 2:
                                line_geoms.append(LineString(pts))
                                cad_lines_file += 1

                        if line_geoms:
                            parcelas.append({"talhao": talhao_name_base, "geoms": line_geoms})
                total_cad_lines += cad_lines_file

                file_reports.append({
                    "filename": input_filenames[idx - 1] if idx - 1 < len(input_filenames) else safe_name,
                    "polygons_extracted": poly_idx_file,
                    "cad_lines_extracted": cad_lines_file,
                    **netinfo,
                })

            except ET.ParseError as e:
                file_reports.append({
                    "filename": input_filenames[idx - 1] if idx - 1 < len(input_filenames) else safe_name,
                    "polygons_extracted": 0,
                    **netinfo,
                    "parse_error": str(e),
                })
            except Exception as e:
                file_reports.append({
                    "filename": input_filenames[idx - 1] if idx - 1 < len(input_filenames) else safe_name,
                    "polygons_extracted": 0,
                    **netinfo,
                    "process_error": str(e),
                })

        if not parcelas and markers:
            kml_str = """<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
        <Document>
            <name>KML Unifier — markers</name>
        </Document>
        </kml>"""
            preview_geojson = {"type": "FeatureCollection", "features": markers}
            input_preview_geojson = {"type": "FeatureCollection", "features": markers}
            metrics = {
                "output_polygons": 0,
                "merged_polygons": 0,
                "input_area_m2": 0,
                "input_area_ha": 0,
                "output_area_m2": 0,
                "output_area_ha": 0,
            }

        elif not parcelas and not markers:
            raise ValueError("Nenhum polígono, linha ou marcador válido encontrado nos arquivos KML.")

        else:
            job_metrics = job.metrics or {}
            merge_mode = (job_metrics.get("merge_mode") or "union").lower().strip()

            if merge_mode not in ("union", "no_union", "concat_only"):
                merge_mode = "union"

            if merge_mode == "concat_only":
                (
                    kml_str,
                    metrics,
                    preview_geojson,
                    input_preview_geojson,
                    total_polygons_concat,
                    total_markers_concat,
                ) = build_concat_only_kml(resolved_file_entries)

                total_polygons = total_polygons_concat
                debug_geojson = None

            elif total_polygons == 0 and total_cad_lines > 0:
                (
                    kml_str,
                    metrics,
                    preview_geojson,
                    input_preview_geojson,
                ) = build_line_merge_kml(
                    parcelas,
                    gap_m=tol_m,
                )

                debug_geojson = None

                if markers:
                    preview_geojson["features"] = (preview_geojson.get("features") or []) + markers
                    input_preview_geojson["features"] = (input_preview_geojson.get("features") or []) + markers

            elif merge_mode == "no_union":
                kml_str, metrics, debug_geojson = merge_no_flood_not_union(
                    parcelas,
                    tol_m=tol_m,
                    corridor_width_m=corridor_width_m,
                    return_metrics=True,
                )

                preview_geojson = view._kml_str_to_geojson(kml_str)

                if markers:
                    preview_geojson["features"] = (preview_geojson.get("features") or []) + markers

                if debug_geojson:
                    extra_feats = (debug_geojson.get("features") or [])
                    if extra_feats:
                        preview_geojson["features"] = (preview_geojson.get("features") or []) + extra_feats

                input_preview_geojson = view._parcelas_to_geojson(parcelas)

                if markers:
                    input_preview_geojson["features"] = (input_preview_geojson.get("features") or []) + markers

            else:
                kml_str, metrics = merge_no_flood(
                    parcelas,
                    tol_m=tol_m,
                    corridor_width_m=corridor_width_m,
                    return_metrics=True,
                )

                debug_geojson = None

                preview_geojson = view._kml_str_to_geojson(kml_str)

                if markers:
                    preview_geojson["features"] = (preview_geojson.get("features") or []) + markers

                input_preview_geojson = view._parcelas_to_geojson(parcelas)

                if markers:
                    input_preview_geojson["features"] = (input_preview_geojson.get("features") or []) + markers

        kml_str = view._append_marker_placemarks_to_kml(kml_str, markers)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kml_unions/union_{ts}_{uuid.uuid4().hex[:6]}.kml"
        saved_path = default_storage.save(filename, ContentFile((kml_str or "").encode("utf-8")))
        
        # -----------------------
        # Analytics: WeeklyUsage (somente sucesso)
        # -----------------------
        weekly_used = None
        if job.user_id:
            today = timezone.localdate()
            year, week_num, _ = today.isocalendar()
            week_key = f"{year}{week_num:02d}"

            with transaction.atomic():
                usage, _ = WeeklyUsage.objects.select_for_update().get_or_create(
                    user=job.user,
                    week=week_key,
                    defaults={"count": 0},
                )
                usage.count += 1
                usage.save(update_fields=["count", "updated_at"])
                weekly_used = usage.count

        meta = {
            "request_id": request_id,
            "created_at": timezone.now().isoformat(),
            "tol_m": tol_m,
            "corridor_width_m": corridor_width_m,
            "total_files": len(input_storage_paths),
            "total_polygons": total_polygons,
            "metrics": metrics or {},
            "files_report": file_reports or [],
            "input_filenames": input_filenames,
            "input_storage_paths": input_storage_paths,
            "output_storage_path": saved_path,
            "total_markers": len([f for f in markers if (f.get("geometry") or {}).get("type") == "Point"]),
            "preview_geojson": preview_geojson,
            "input_preview_geojson": input_preview_geojson,
            "total_cad_lines": total_cad_lines,
        }

        meta_path = f"kml_unions/{request_id}/meta/meta.json"
        default_storage.save(
            meta_path,
            ContentFile(json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")),
        )

        job.status = getattr(KMLMergeJob, "STATUS_SUCCESS", "success")
        job.total_polygons = total_polygons
        job.output_polygons = (metrics or {}).get("output_polygons")
        job.merged_polygons = (metrics or {}).get("merged_polygons")
        job.input_area_m2 = (metrics or {}).get("input_area_m2")
        job.input_area_ha = (metrics or {}).get("input_area_ha")
        job.output_area_m2 = (metrics or {}).get("output_area_m2")
        job.output_area_ha = (metrics or {}).get("output_area_ha")
        job.storage_path = saved_path
        job.meta_storage_path = meta_path
        job.metrics = {
            **(job.metrics or {}),
            **(metrics or {}),
            "files_report": file_reports,
            "preview_geojson": preview_geojson,
            "input_preview_geojson": input_preview_geojson,
            "total_markers": len([f for f in markers if (f.get("geometry") or {}).get("type") == "Point"]),
            "total_cad_lines": total_cad_lines,
            "weekly_used": weekly_used,
        }
        job.save()

    except Exception as e:
        try:
            job = KMLMergeJob.objects.get(id=job_id)
            job.status = getattr(KMLMergeJob, "STATUS_ERROR", "error")
            if hasattr(job, "error_message"):
                job.error_message = str(e)[:2000]
                job.save(update_fields=["status", "error_message"])
            else:
                job.metrics = {**(job.metrics or {}), "error_message": str(e)}
                job.save(update_fields=["status", "metrics"])
        except Exception:
            pass
    finally:
        close_old_connections()

def get_client_ip(request):
    # Cloudflare / proxies comuns
    cf = (request.META.get("HTTP_CF_CONNECTING_IP") or "").strip()
    if cf:
        return cf

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # pega o primeiro (cliente original)
        return xff.split(",")[0].strip()

    ip = (request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "").strip()
    return ip or None

def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_global  # evita private/loopback/reserved
    except Exception:
        return False

def geo_country_from_ip(ip: str):
    """
    Retorna (country_code_iso2, country_name) ou (None, None).
    ipapi.co é simples e bom o bastante p/ isso.
    """
    try:
        r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=5.0)
        if r.status_code != 200:
            return None, None
        data = r.json() or {}
        cc = (data.get("country") or "").strip() or None
        cn = (data.get("country_name") or "").strip() or None
        if cc and len(cc) == 2:
            return cc.upper(), cn
        return None, None
    except Exception:
        return None, None

def ensure_country_on_bp(bp, request):
    """
    Só seta uma vez (quando estiver vazio).
    Não falha a request se der ruim na geo.
    """
    # debug temporário (depois remove)
    logger.warning("IP DEBUG xff=%s xreal=%s remote=%s cf=%s",
        request.META.get("HTTP_X_FORWARDED_FOR"),
        request.META.get("HTTP_X_REAL_IP"),
        request.META.get("REMOTE_ADDR"),
        request.META.get("HTTP_CF_CONNECTING_IP"),
    )

    if not bp or getattr(bp, "country", None):
        return

    ip = get_client_ip(request)
    if not ip:
        return

    # ✅ filtro leve: bloqueia só IPs obviamente inválidos/internos
    try:
        addr = ipaddress.ip_address(ip)
        if not addr.is_global:
            return
    except Exception:
        return

    cc, cn = geo_country_from_ip(ip)
    if not cc:
        return

    bp.country = cc
    bp.country_name = cn
    bp.country_source = "ip"
    bp.country_set_at = timezone.now()
    bp.save(update_fields=["country", "country_name", "country_source", "country_set_at"])

def ensure_country_from_anon_jobs(bp, anon_id: str):
    if not bp or bp.country or not anon_id:
        return False

    job = (KMLMergeJob.objects
            .filter(anon_id=anon_id)
            .exclude(visitor_country__isnull=True)
            .exclude(visitor_country="")
            .order_by("-created_at")
            .first())
    if not job:
        return False

    bp.country = (job.visitor_country or "").upper().strip() or None
    bp.country_name = (job.visitor_country_name or "").strip() or None
    if not bp.country:
        return False
    bp.country_name = job.visitor_country_name
    bp.country_source = "anon_ip"
    bp.country_set_at = timezone.now()
    bp.save(update_fields=["country","country_name","country_source","country_set_at","updated_at"])
    return True

class KMLAnonThrottle(AnonRateThrottle):
    rate = "20/hour"

class KMLUserThrottle(UserRateThrottle):
    rate = "200/hour"




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
PREPAID_CREDITS_PER_PACK = 5
PREPAID_SINGLE_CREDIT=1


def _get_firebase_uid_from_user(user):
    # ajuste conforme o seu User model / FirebaseAuthentication
    return (
        getattr(user, "firebase_uid", None)
        or getattr(user, "uid", None)
        or getattr(user, "firebaseUid", None)
    )

def ensure_billing_profile(user, request=None):
    """
    Garante que existe BillingProfile salvo e retorna ele.
    Se não conseguir inferir firebase_uid, retorna None.
    """
    if not user:
        return None

    bp = getattr(user, "billing", None)
    if bp and getattr(bp, "pk", None):
        if request and not getattr(bp, "country", None):
            anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None
            if anon_id:
                try:
                    if ensure_country_from_anon_jobs(bp, anon_id):
                        return bp
                except Exception:
                    pass
            try:
                ensure_country_on_bp(bp, request)
            except Exception:
                pass
        return bp

    firebase_uid = _get_firebase_uid_from_user(user)
    if not firebase_uid:
        return None

    bp, _ = BillingProfile.objects.get_or_create(
        user=user,
        defaults={"firebase_uid": firebase_uid},
    )
    if request:
        anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None
        if anon_id:
            try:
                if ensure_country_from_anon_jobs(bp, anon_id):
                    return bp
            except Exception:
                pass

        # fallback IP do request autenticado
        try:
            ensure_country_on_bp(bp, request)
        except Exception:
            pass
    return bp

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
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        bp = ensure_billing_profile(request.user, request=request)
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
            "use_case": bp.use_case or "",
            "usage_frequency": bp.usage_frequency or "",
            "onboarding_completed_at": bp.onboarding_completed_at.isoformat() if bp.onboarding_completed_at else None,
            "onboarding_skipped_count": int(bp.onboarding_skipped_count or 0),
            "free_unlock_used": bool(getattr(bp, "free_unlock_used", False)),

        })

# (mantém seus imports/constantes/helpers já existentes no arquivo)
# - NETWORKLINK_HREF_RE
# - DEFAULT_ALLOWED_HOST_SUFFIXES, etc
# - _debug_enabled, _save_kml_debug_bundle_storage
# - NetworkLinkResolveError
# - e todos os helpers _resolve_networklink_if_needed, _findall_anyns, etc (já estão na sua classe)




class KMLUnionView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    authentication_classes = (FirebaseAuthentication,)  # pode deixar, mas não obriga
    permission_classes = (AllowAny,)
    throttle_classes = [KMLAnonThrottle, KMLUserThrottle]

    
    
    def clamp(self, value, min_value=None, max_value=None):
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    def _sanitize_kml_xml_bytes(self, xml_bytes: bytes) -> bytes:
        """
        Corrige KMLs malformados que usam `xsi:*` (ex.: xsi:schemaLocation)
        sem declarar `xmlns:xsi` na tag <kml>.

        Não altera arquivos válidos.
        """
        if not xml_bytes:
            return xml_bytes

        try:
            text = xml_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return xml_bytes

        # Só tenta corrigir se houver uso de xsi: e não existir declaração do namespace
        has_xsi_usage = ("xsi:" in text)
        has_xsi_decl = ('xmlns:xsi=' in text)

        if has_xsi_usage and not has_xsi_decl:
            fixed_text = re.sub(
                r"<kml\b",
                '<kml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
                text,
                count=1,
                flags=re.IGNORECASE,
            )
            if fixed_text != text:
                logger.warning("[KML] XML sanitizado automaticamente: xmlns:xsi adicionado.")
                return fixed_text.encode("utf-8")

        return xml_bytes


    def _safe_parse_xml(self, xml_bytes: bytes):
        """
        Faz parse normal. Se falhar por XML/KML malformado simples,
        tenta sanitizar e parsear novamente.

        Mantém o comportamento antigo para arquivos válidos.
        """
        try:
            return ET.fromstring(xml_bytes)
        except ET.ParseError:
            fixed_bytes = self._sanitize_kml_xml_bytes(xml_bytes)
            if fixed_bytes == xml_bytes:
                raise
            return ET.fromstring(fixed_bytes)

    # ---------- helpers namespace-agnostic ----------
    def _extract_point_placemarks_as_geojson(self, root, fallback_name="Marker"):
        feats = []
        idx = 0

        placemarks = list(self._findall_anyns(root, "Placemark"))
        if not placemarks:
            placemarks = [root]

        for pm in placemarks:
            # ignora placemark que já tem Polygon (senão duplica nome)
            has_poly = any(True for _ in self._findall_anyns(pm, "Polygon"))
            if has_poly:
                continue

            pt = self._first_anyns(pm, "Point")
            if pt is None:
                continue

            coord_el = self._first_anyns(pt, "coordinates")
            if coord_el is None or not (coord_el.text and coord_el.text.strip()):
                continue

            # coordinates: lon,lat[,alt]
            token = coord_el.text.strip().split()[0]
            parts = token.split(",")
            if len(parts) < 2:
                continue

            try:
                lon = float(parts[0])
                lat = float(parts[1])
            except Exception:
                continue

            name_el = self._first_anyns(pm, "name")
            nm = (name_el.text or "").strip() if name_el is not None else ""
            if not nm:
                idx += 1
                nm = f"{fallback_name} {idx}"

            feats.append({
                "type": "Feature",
                "properties": {"name": nm, "kind": "marker"},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            })

        return feats


    def _append_marker_placemarks_to_kml(self, kml_str: str, marker_features: list) -> str:
        """
        Insere os markers como <Placemark> dentro do <Document>.
        Não altera o polígono merged.
        """
        if not kml_str or not marker_features:
            return kml_str

        placemarks_xml = []
        for f in marker_features:
            g = (f or {}).get("geometry") or {}
            if g.get("type") != "Point":
                continue
            coords = g.get("coordinates") or []
            if len(coords) < 2:
                continue

            lon, lat = coords[0], coords[1]
            name = ((f.get("properties") or {}).get("name") or "Marker").strip()

            placemarks_xml.append(
                f"""
        <Placemark>
        <name>{self._xml_escape(name)}</name>
        <Point><coordinates>{lon},{lat},0</coordinates></Point>
        </Placemark>
                """.rstrip()
            )

        if not placemarks_xml:
            return kml_str

        insert_block = "\n" + "\n".join(placemarks_xml) + "\n"

        # tenta inserir antes de </Document>, senão antes de </kml>
        if "</Document>" in kml_str:
            return kml_str.replace("</Document>", insert_block + "</Document>", 1)
        if "</kml>" in kml_str:
            return kml_str.replace("</kml>", insert_block + "</kml>", 1)
        return kml_str


    def _xml_escape(self, s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )



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
            root = self._safe_parse_xml(kml_str.encode("utf-8", errors="ignore"))
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
            # 1) modo normal: coords (list[{lat,lon}])
            coords = p.get("coords")
            if coords:
                ring = []
                for c in coords:
                    try:
                        ring.append([float(c["longitude"]), float(c["latitude"])])
                    except Exception:
                        continue

                if len(ring) >= 3:
                    if ring[0] != ring[-1]:
                        ring.append(ring[0])

                    idx += 1
                    features.append({
                        "type": "Feature",
                        "properties": {"name": p.get("talhao"), "idx": idx, "kind": "input_polygon"},
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    })
                continue

            # 2) modo CAD: geoms (list[LineString])
            geoms = p.get("geoms") or []
            for g in geoms:
                try:
                    pts = list(getattr(g, "coords", []) or [])
                except Exception:
                    pts = []
                if len(pts) < 2:
                    continue

                idx += 1
                features.append({
                    "type": "Feature",
                    "properties": {"name": p.get("talhao"), "idx": idx, "kind": "input_line"},
                    "geometry": {"type": "LineString", "coordinates": [[float(x), float(y)] for (x, y) in pts]},
                })

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
    
    def _safe_filename(self, name: str) -> str:
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

    # def post(self, request, *args, **kwargs):
    #     week_key = None
    #     weekly_used = None
    #     request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    #     FREE_MAX_FILES = 20
    #     PAID_MAX_FILES = 300
    #     MAX_TOTAL_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

    #     files = request.FILES.getlist("files")
    #     mode = request.data.get("merge_mode", "union")
    #     print('[MODE] - ', mode)

    #     if not files:
    #         return Response(
    #             {"detail": "Nenhum arquivo enviado. Use o campo 'files'."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )

    #     user = request.user if getattr(request.user, "is_authenticated", False) else None
    #     bp = ensure_billing_profile(user, request=request) if user else None

    #     plan_for_limits = (getattr(bp, "plan", None) or "free").lower().strip()
    #     is_paid_plan = bool(getattr(bp, "is_unlimited", False)) or plan_for_limits in (
    #         "pro_monthly",
    #         "pro_yearly",
    #         "prepaid",
    #         "prepaid_unlimited",
    #     )

    #     max_files_allowed = PAID_MAX_FILES if is_paid_plan else FREE_MAX_FILES

    #     if len(files) > max_files_allowed:
    #         return Response(
    #             {
    #                 "detail": f"Máximo de {max_files_allowed} arquivos por merge para o seu plano."
    #             },
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )

    #     total_size = sum((getattr(f, "size", 0) or 0) for f in files)
    #     if total_size > MAX_TOTAL_SIZE_BYTES:
    #         return Response(
    #             {"detail": "Tamanho total excede 20 MB por merge."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )

    #     # segue o fluxo normal

    #     anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None
    #     visitor_country = None
    #     visitor_country_name = None
    #     visitor_ip = None

    #     try:
    #         visitor_ip = get_client_ip(request)
    #         if visitor_ip:
    #             try:
    #                 if ipaddress.ip_address(visitor_ip).is_global:
    #                     cc, cn = geo_country_from_ip(visitor_ip)
    #                     visitor_country, visitor_country_name = cc, cn
    #             except Exception:
    #                 pass
    #     except Exception:
    #         pass


    #     # Semana (analytics)
    #     today = timezone.localdate()
    #     year, week_num, _ = today.isocalendar()
    #     week_key = f"{year}{week_num:02d}"

    #     debug_enabled = False
    #     try:
    #         debug_enabled = _debug_enabled()
    #     except Exception:
    #         debug_enabled = False

    #     # tol_m
    #     try:
    #         tol_m = float(request.data.get("tol_m", 20.0))
    #         print("[TOL_M] tol_m received from FrontEnd:", tol_m)
    #     except (TypeError, ValueError):
    #         tol_m = 20.0
    #     tol_m = self.clamp(tol_m, min_value=1.0)

    #     # corridor_width_m
    #     # corridor_width_m
    #     raw_corridor = request.data.get("corridor_width_m", None)

    #     if raw_corridor is None or str(raw_corridor).strip() == "":
    #         corridor_width_m = 0.0
    #     else:
    #         try:
    #             corridor_width_m = float(raw_corridor)
    #         except (TypeError, ValueError):
    #             corridor_width_m = 0.0

    #     corridor_width_m = self.clamp(corridor_width_m, min_value=0.0, max_value=500.0)


    #     parcelas = []
    #     total_polygons = 0
    #     debug_files = []
    #     file_reports = []
    #     input_storage_paths = []  # paths dos inputs persistidos
    #     markers = []   # <-- NOVO: features Point preservadas

    #     try:
    #         # -----------------------
    #         # Processar cada input
    #         # -----------------------
    #         for idx, uploaded in enumerate(files, start=1):
    #             raw_bytes = uploaded.read()
                
    #             raw_bytes = self._maybe_extract_kml_from_kmz(raw_bytes)
                
    #             try:
    #                 # Se o arquivo original era .kmz, trocamos para .kml no nome salvo, 
    #                 # já que extraímos o conteúdo.
    #                 original_name = uploaded.name
    #                 if original_name.lower().endswith(".kmz"):
    #                     safe_name = os.path.splitext(original_name)[0] + ".kml"
    #                 else:
    #                     safe_name = self._safe_filename(original_name)
    #             except Exception:
    #                 safe_name = f"input_{idx}.kml"

    #             print("\n" + "=" * 60)
    #             print("arquivo recebido Nº:", idx)
    #             print(f"📄 Recebido arquivo: {uploaded.name}")
    #             print(f"📦 Tamanho: {uploaded.size} bytes")
    #             print("-" * 60)
    #             try:
    #                 snippet = raw_bytes[:500].decode("utf-8", errors="ignore")
    #             except Exception:
    #                 snippet = str(raw_bytes[:200])
    #             print("🔍 Início do arquivo (snippet):")
    #             print(snippet)
    #             print("-" * 60)

    #             if debug_enabled:
    #                 debug_files.append((uploaded.name, raw_bytes))

    #             # --- NetworkLink support ---
    #             try:
    #                 resolved_bytes, netinfo = self._resolve_networklink_if_needed(raw_bytes, uploaded.name)
    #             except Exception as e:
    #                 resolved_bytes, netinfo = raw_bytes, {
    #                     "networklink_detected": True,
    #                     "networklink_resolved": False,
    #                     "networklink_href": None,
    #                     "networklink_error": f"resolver_crash: {type(e).__name__}: {e}",
    #                 }

    #             if netinfo.get("networklink_detected"):
    #                 print(
    #                     f"[NETLINK] detected={netinfo.get('networklink_detected')} "
    #                     f"resolved={netinfo.get('networklink_resolved')} "
    #                     f"href={netinfo.get('networklink_href')}"
    #                 )
    #                 if netinfo.get("networklink_error"):
    #                     print(f"[NETLINK] error={netinfo.get('networklink_error')}")

    #             # -----------------------
    #             # Persistir input resolvido no storage
    #             # -----------------------
    #             input_path = f"kml_unions/{request_id}/inputs/{idx:02d}_{safe_name}"
    #             try:
    #                 default_storage.save(input_path, ContentFile(resolved_bytes))
    #                 input_storage_paths.append(input_path)
    #             except Exception as e:
    #                 print(f"[INPUT_SAVE] Falha ao salvar input {uploaded.name}: {e}")

    #             # -----------------------
    #             # Extrair polígonos
    #             # -----------------------
    #             poly_idx_file = 0
    #             cad_lines_file = 0
    #             try:
    #                 root = ET.fromstring(resolved_bytes)
    #                 # ✅ NOVO: extrai markers (Point) e preserva
    #                 try:
    #                     base_marker_name = os.path.splitext(uploaded.name)[0]
    #                     markers.extend(self._extract_point_placemarks_as_geojson(root, fallback_name=base_marker_name))
    #                 except Exception as e:
    #                     print(f"⚠️ Falha ao extrair markers de {uploaded.name}: {e}")


    #                 placemarks = list(self._findall_anyns(root, "Placemark"))
    #                 if not placemarks:
    #                     placemarks = [root]

    #                 for placemark in placemarks:
    #                     name_el = self._first_anyns(placemark, "name")
    #                     talhao_name_base = (name_el.text or "").strip() if name_el is not None else ""

    #                     if not talhao_name_base:
    #                         talhao_name_base = os.path.splitext(uploaded.name)[0]

    #                     # ✅ detecta se tem Polygon nesse placemark
    #                     has_poly = any(True for _ in self._findall_anyns(placemark, "Polygon"))

    #                     poly_idx_pm = 0

    #                     # -----------------------
    #                     # 1) fluxo atual: Polygon -> coords
    #                     # -----------------------
    #                     for poly in self._findall_anyns(placemark, "Polygon"):
    #                         outer = self._first_anyns(poly, "outerBoundaryIs")
    #                         if outer is None:
    #                             continue

    #                         lr = self._first_anyns(outer, "LinearRing")
    #                         if lr is None:
    #                             continue

    #                         coord_el = self._first_anyns(lr, "coordinates")
    #                         if coord_el is None or not (coord_el.text and coord_el.text.strip()):
    #                             continue

    #                         coords = self._parse_kml_coordinates_text(coord_el.text)
    #                         if len(coords) < 3:
    #                             continue

    #                         poly_idx_pm += 1
    #                         poly_idx_file += 1
    #                         total_polygons += 1

    #                         talhao_name = talhao_name_base if poly_idx_pm == 1 else f"{talhao_name_base}_{poly_idx_pm}"
    #                         parcelas.append({"talhao": talhao_name, "coords": coords})

    #                     # -----------------------
    #                     # 2) ✅ NOVO: fallback CAD (LineString/LinearRing)
    #                     #    Só entra se NÃO houver Polygon no placemark.
    #                     # -----------------------
    #                     if not has_poly:
    #                         line_geoms = []

    #                         # CAD costuma vir como <LineString><coordinates>...</coordinates></LineString>
    #                         for ls in self._findall_anyns(placemark, "LineString"):
    #                             coord_el = self._first_anyns(ls, "coordinates")
    #                             if coord_el is None or not (coord_el.text and coord_el.text.strip()):
    #                                 continue

    #                             coords_ll = self._parse_kml_coordinates_text(coord_el.text)
    #                             if len(coords_ll) < 2:
    #                                 continue

    #                             pts = [(float(p["longitude"]), float(p["latitude"])) for p in coords_ll]
    #                             if len(pts) >= 2:
    #                                 line_geoms.append(LineString(pts))
    #                                 cad_lines_file += 1

    #                         # Às vezes CAD vem como <LinearRing> SOLTO (sem Polygon)
    #                         for lr in self._findall_anyns(placemark, "LinearRing"):
    #                             coord_el = self._first_anyns(lr, "coordinates")
    #                             if coord_el is None or not (coord_el.text and coord_el.text.strip()):
    #                                 continue

    #                             coords_ll = self._parse_kml_coordinates_text(coord_el.text)
    #                             if len(coords_ll) < 2:
    #                                 continue

    #                             pts = [(float(p["longitude"]), float(p["latitude"])) for p in coords_ll]
    #                             if len(pts) >= 2:
    #                                 line_geoms.append(LineString(pts))
    #                                 cad_lines_file += 1

    #                         # ✅ se achou linhas, cria 1 “parcela CAD” para o geo_merge converter em Polygon(s)
    #                         if line_geoms:
    #                             parcelas.append({"talhao": talhao_name_base, "geoms": line_geoms})

    #                             # opcional: report (não mexe no total_polygons pq ainda não sabemos quantos polígonos vai gerar)
    #                             # você pode contabilizar como "cad_shapes" se quiser debugar:
    #                             # poly_idx_file += 0
    #                 print(f"✅ Polígonos extraídos desse arquivo: {poly_idx_file}")

    #                 file_reports.append(
    #                     {
    #                         "filename": uploaded.name,
    #                         "polygons_extracted": poly_idx_file,
    #                         "cad_lines_extracted": cad_lines_file,
    #                         **netinfo,
    #                     }
    #                 )

    #             except ET.ParseError as e:
    #                 print(f"❌ Erro de parse XML em {uploaded.name}: {e}")
    #                 file_reports.append(
    #                     {
    #                         "filename": uploaded.name,
    #                         "polygons_extracted": 0,
    #                         **netinfo,
    #                         "parse_error": str(e),
    #                     }
    #                 )
    #             except Exception as e:
    #                 print(f"❌ Erro ao processar KML {uploaded.name}: {e}")
    #                 file_reports.append(
    #                     {
    #                         "filename": uploaded.name,
    #                         "polygons_extracted": 0,
    #                         **netinfo,
    #                         "process_error": str(e),
    #                     }
    #                 )

    #         print("=" * 60)
    #         print(f"📊 Total de polígonos extraídos de todos os arquivos: {total_polygons}")
    #         print(f"📊 Total de parcelas geradas: {len(parcelas)}")
    #         print("=" * 60)

    #         # ✅ Se não há polígonos, mas há markers, exporta markers-only
    #         if not parcelas and markers:
    #             # gera KML só com markers (sem merge)
    #             kml_str = """<?xml version="1.0" encoding="UTF-8"?>
    #                 <kml xmlns="http://www.opengis.net/kml/2.2">
    #                     <Document>
    #                         <name>KML Unifier — markers</name>
    #                     </Document>
    #                 </kml>
    #             """

    #             # previews
    #             preview_geojson = {"type": "FeatureCollection", "features": markers}
    #             input_preview_geojson = {"type": "FeatureCollection", "features": markers}

    #             metrics = {
    #                 "output_polygons": 0,
    #                 "merged_polygons": 0,
    #                 "input_area_m2": 0,
    #                 "input_area_ha": 0,
    #                 "output_area_m2": 0,
    #                 "output_area_ha": 0,
    #             }

    #             # segue para salvar output e responder (pula merge)
    #             goto_merge = False
    #         else:
    #             goto_merge = True

    #         # ✅ Se não há nada (nem polygon, nem marker)
    #         if not parcelas and not markers:
    #             return Response(
    #                 {
    #                     "detail": "Nenhum polígono ou marcador válido encontrado nos arquivos KML.",
    #                     "request_id": request_id,
    #                     "files_report": file_reports,
    #                 },
    #                 status=status.HTTP_400_BAD_REQUEST,
    #             )


    #         ## -----------------------
    #         # Merge
    #         # -----------------------
    #         if goto_merge:
    #             ## -----------------------
    #             # Merge
    #             # -----------------------
    #             try:
    #                 merge_mode = (mode or "union").lower().strip()
    #                 print("[MERGE HERE MODE] -", merge_mode)

    #                 debug_geojson = None

    #                 if merge_mode == "no_union":
    #                     kml_str, metrics, debug_geojson = merge_no_flood_not_union(
    #                         parcelas,
    #                         tol_m=tol_m,
    #                         corridor_width_m=corridor_width_m,
    #                         return_metrics=True,
    #                     )
    #                 else:
    #                     kml_str, metrics = merge_no_flood(
    #                         parcelas,
    #                         tol_m=tol_m,
    #                         corridor_width_m=corridor_width_m,
    #                         return_metrics=True,
    #                     )

    #                 print("[KML_OUT] snippet:", (kml_str or "")[:500])

    #                 preview_geojson = self._kml_str_to_geojson(kml_str)

    #                 # ✅ adiciona markers no preview
    #                 if markers:
    #                     preview_geojson["features"] = (preview_geojson.get("features") or []) + markers

    #                 # ✅ injeta as linhas se existirem
    #                 if debug_geojson:
    #                     extra_feats = (debug_geojson.get("features") or [])
    #                     if extra_feats:
    #                         preview_geojson["features"] = (preview_geojson.get("features") or []) + extra_feats

    #                 input_preview_geojson = self._parcelas_to_geojson(parcelas)
    #                 if markers:
    #                     input_preview_geojson["features"] = (input_preview_geojson.get("features") or []) + markers

    #             except Exception as e:
    #                 print(f"❌ Erro interno no merge_no_flood: {e}")
    #                 return Response(
    #                     {
    #                         "detail": "Erro interno ao unificar polígonos.",
    #                         "request_id": request_id,
    #                         "files_report": file_reports,
    #                     },
    #                     status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #                 )

    #         # ✅ NOVO: adiciona markers no KML para download
    #         kml_str = self._append_marker_placemarks_to_kml(kml_str, markers)

    #         # -----------------------
    #         # Salvar output
    #         # -----------------------
    #         ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    #         filename = f"kml_unions/union_{ts}_{uuid.uuid4().hex[:6]}.kml"
    #         saved_path = default_storage.save(filename, ContentFile((kml_str or "").encode("utf-8")))
            
            


    #         # URL (fallback)
    #         try:
    #             download_url = default_storage.url(saved_path)
    #         except NotImplementedError:
    #             media_url = settings.MEDIA_URL
    #             if not media_url.endswith("/"):
    #                 media_url += "/"
    #             download_url = request.build_absolute_uri(media_url + saved_path)
    #         except Exception:
    #             download_url = None

    #         # -----------------------
    #         # Analytics: WeeklyUsage
    #         # -----------------------
    #         if user:
    #             with transaction.atomic():
    #                 usage, _ = WeeklyUsage.objects.select_for_update().get_or_create(
    #                     user=user,
    #                     week=week_key,
    #                     defaults={"count": 0},
    #                 )
    #                 usage.count += 1
    #                 usage.save(update_fields=["count", "updated_at"])
    #                 weekly_used = usage.count
    #         else:
    #             weekly_used = None


    #         # -----------------------
    #         # Persistir Job + Meta
    #         # -----------------------
    #         job = None
    #         try:
    #             import json  # garante import aqui
    #             input_filenames = [getattr(f, "name", "") for f in files]
    #             plan_now = getattr(bp, "plan", None) if bp else ("anonymous" if not user else "free")

    #             meta = {
    #                 "request_id": request_id,
    #                 "user_email": getattr(request.user, "email", None),
    #                 "created_at": timezone.now().isoformat(),
    #                 "tol_m": tol_m,
    #                 "corridor_width_m": corridor_width_m,
    #                 "total_files": len(files),
    #                 "total_polygons": total_polygons,
    #                 "metrics": metrics or {},
    #                 "files_report": file_reports or [],
    #                 "input_filenames": input_filenames,
    #                 "input_storage_paths": input_storage_paths,
    #                 "output_storage_path": saved_path,
    #                 "total_markers": len([f for f in markers if (f.get("geometry") or {}).get("type") == "Point"])
    #             }
                

    #             meta_path = f"kml_unions/{request_id}/meta/meta.json"
    #             default_storage.save(
    #                 meta_path,
    #                 ContentFile(json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")),
    #             )

    #             job = KMLMergeJob.objects.create(
    #                 user=user,
    #                 anon_id=anon_id,
    #                 plan=(plan_now or getattr(bp, "plan", "anonymous") or "anonymous"),
    #                 request_id=request_id,
    #                 status=KMLMergeJob.STATUS_SUCCESS,
    #                 tol_m=tol_m,
    #                 corridor_width_m=corridor_width_m,
    #                 total_files=len(files),
    #                 total_polygons=total_polygons,
    #                 output_polygons=(metrics or {}).get("output_polygons"),
    #                 merged_polygons=(metrics or {}).get("merged_polygons"),
    #                 input_area_m2=(metrics or {}).get("input_area_m2"),
    #                 input_area_ha=(metrics or {}).get("input_area_ha"),
    #                 output_area_m2=(metrics or {}).get("output_area_m2"),
    #                 output_area_ha=(metrics or {}).get("output_area_ha"),
    #                 storage_path=saved_path,
    #                 metrics=metrics or {},
    #                 input_filenames=input_filenames,
    #                 input_storage_paths=input_storage_paths,
    #                 meta_storage_path=meta_path,

    #                 visitor_ip=visitor_ip,
    #                 visitor_country=visitor_country,
    #                 visitor_country_name=visitor_country_name,
    #             )
    #         except Exception as e:
    #             print(f"[KML_HISTORY] Falha ao salvar histórico do merge {request_id}: {e}")

    #         # -----------------------
    #         # Debug bundle (opcional)
    #         # -----------------------
    #         if debug_enabled:
    #             try:
    #                 Thread(
    #                     target=_save_kml_debug_bundle_storage,
    #                     args=(request_id, tol_m, corridor_width_m, debug_files, kml_str, metrics),
    #                     daemon=True,
    #                 ).start()
    #             except Exception:
    #                 pass

    #         # -----------------------
    #         # Resposta / gating
    #         # -----------------------
    #         if bp and getattr(bp, "pk", None):
    #             try:
    #                 bp.refresh_from_db()
    #             except Exception:
    #                 pass

    #         plan = (getattr(bp, "plan", None) or "free").lower().strip()
    #         prepaid_left = int(getattr(bp, "prepaid_credits", 0) or 0)
    #         free_left = int(getattr(bp, "free_monthly_credits", 0) or 0)
    #         credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0)

    #         is_unlimited = bool(getattr(bp, "is_unlimited", False)) or plan in ("pro_monthly", "pro_yearly")

    #         download_available = bool(is_unlimited) or prepaid_left > 0
    #         download_url_out = download_url if download_available else None
            
    #         if not user:
    #             plan = (getattr(bp, "plan", None) or "anonymous").lower().strip() if bp else "anonymous"
    #             download_available = False
    #             download_url_out = None

    #         return Response(
    #             {
    #                 "request_id": request_id,
    #                 "job_id": str(job.id) if job else None,
    #                 "download_available": download_available,
    #                 "download_url": download_url_out,  # null para free

    #                 "total_polygons": total_polygons,
    #                 "total_files": len(files),
    #                 "tol_m": tol_m,
    #                 "corridor_width_m": corridor_width_m,
    #                 "output_polygons": (metrics or {}).get("output_polygons"),
    #                 "merged_polygons": (metrics or {}).get("merged_polygons"),
    #                 "input_area_m2": (metrics or {}).get("input_area_m2"),
    #                 "input_area_ha": (metrics or {}).get("input_area_ha"),
    #                 "output_area_m2": (metrics or {}).get("output_area_m2"),
    #                 "output_area_ha": (metrics or {}).get("output_area_ha"),

    #                 "plan": plan,
    #                 "week": week_key,
    #                 "weekly_used": weekly_used,
    #                 "free_monthly_credits": free_left,
    #                 "prepaid_credits": prepaid_left,
    #                 "credits_used_total": credits_used_total,

    #                 "files_report": file_reports,
    #                 "input_preview_geojson": input_preview_geojson,
    #                 "preview_geojson": preview_geojson,
    #                 "total_markers": len([f for f in markers if (f.get("geometry") or {}).get("type") == "Point"]),

    #             },
    #             status=status.HTTP_200_OK,
    #         )

    #     except Exception as e:
    #         return Response(
    #             {"detail": str(e) or "Merge failed.", "code": "MERGE_FAILED"},
    #             status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         )

    def post(self, request, *args, **kwargs):
        week_key = None
        weekly_used = None
        request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        FREE_MAX_FILES = 20
        PAID_MAX_FILES = 300
        MAX_TOTAL_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

        files = request.FILES.getlist("files")
        mode = request.data.get("merge_mode", "union")
        print("[MODE] - ", mode)

        if not files:
            return Response(
                {"detail": "Nenhum arquivo enviado. Use o campo 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user if getattr(request.user, "is_authenticated", False) else None
        bp = ensure_billing_profile(user, request=request) if user else None

        plan_for_limits = (getattr(bp, "plan", None) or "free").lower().strip()
        is_paid_plan = bool(getattr(bp, "is_unlimited", False)) or plan_for_limits in (
            "pro_monthly",
            "pro_yearly",
            "prepaid",
            "prepaid_unlimited",
        )

        max_files_allowed = PAID_MAX_FILES if is_paid_plan else FREE_MAX_FILES

        if len(files) > max_files_allowed:
            return Response(
                {
                    "detail": f"Máximo de {max_files_allowed} arquivos por merge para o seu plano."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_size = sum((getattr(f, "size", 0) or 0) for f in files)
        if total_size > MAX_TOTAL_SIZE_BYTES:
            return Response(
                {"detail": "Tamanho total excede 20 MB por merge."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None
        visitor_country = None
        visitor_country_name = None
        visitor_ip = None

        try:
            visitor_ip = get_client_ip(request)
            if visitor_ip:
                try:
                    if ipaddress.ip_address(visitor_ip).is_global:
                        cc, cn = geo_country_from_ip(visitor_ip)
                        visitor_country, visitor_country_name = cc, cn
                except Exception:
                    pass
        except Exception:
            pass

        # Semana (analytics)
        today = timezone.localdate()
        year, week_num, _ = today.isocalendar()
        week_key = f"{year}{week_num:02d}"

        # tol_m
        try:
            tol_m = float(request.data.get("tol_m", 20.0))
            print("[TOL_M] tol_m received from FrontEnd:", tol_m)
        except (TypeError, ValueError):
            tol_m = 20.0
        tol_m = self.clamp(tol_m, min_value=1.0)

        # corridor_width_m
        raw_corridor = request.data.get("corridor_width_m", None)

        if raw_corridor is None or str(raw_corridor).strip() == "":
            corridor_width_m = 0.0
        else:
            try:
                corridor_width_m = float(raw_corridor)
            except (TypeError, ValueError):
                corridor_width_m = 0.0

        corridor_width_m = self.clamp(corridor_width_m, min_value=0.0, max_value=500.0)

        input_storage_paths = []
        input_filenames = []

        try:
            # -----------------------
            # Persistir inputs para processamento async
            # -----------------------
            for idx, uploaded in enumerate(files, start=1):
                raw_bytes = uploaded.read()

                try:
                    original_name = uploaded.name
                    safe_name = self._safe_filename(original_name)
                except Exception:
                    safe_name = f"input_{idx}.kml"

                input_path = f"kml_unions/{request_id}/inputs/{idx:02d}_{safe_name}"
                default_storage.save(input_path, ContentFile(raw_bytes))

                input_storage_paths.append(input_path)
                input_filenames.append(getattr(uploaded, "name", safe_name))
            
            weekly_used = None
            # -----------------------
            # Criar job em estado queued
            # -----------------------
            plan_now = getattr(bp, "plan", None) if bp else ("anonymous" if not user else "free")
            
            with transaction.atomic():
                job = KMLMergeJob.objects.create(
                    user=user,
                    anon_id=anon_id,
                    plan=(plan_now or getattr(bp, "plan", "anonymous") or "anonymous"),
                    request_id=request_id,
                    status=getattr(KMLMergeJob, "STATUS_QUEUED", "queued"),
                    tol_m=tol_m,
                    corridor_width_m=corridor_width_m,
                    total_files=len(files),
                    total_polygons=0,
                    metrics={
                        "merge_mode": (mode or "union").lower().strip(),
                        "queued_at": timezone.now().isoformat(),
                    },
                    input_filenames=input_filenames,
                    input_storage_paths=input_storage_paths,
                    visitor_ip=visitor_ip,
                    visitor_country=visitor_country,
                    visitor_country_name=visitor_country_name,
                )

                # dispara a thread só depois do commit do banco
                transaction.on_commit(lambda: start_kml_merge_thread(job.id))
            
            # -----------------------
            # Resposta async imediata
            # -----------------------
            if bp and getattr(bp, "pk", None):
                try:
                    bp.refresh_from_db()
                except Exception:
                    pass

            plan = (getattr(bp, "plan", None) or "free").lower().strip()
            prepaid_left = int(getattr(bp, "prepaid_credits", 0) or 0)
            free_left = int(getattr(bp, "free_monthly_credits", 0) or 0)
            credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0)

            if not user:
                plan = (getattr(bp, "plan", None) or "anonymous").lower().strip() if bp else "anonymous"

            return Response(
                {
                    "request_id": request_id,
                    "job_id": str(job.id),
                    "status": getattr(job, "status", "queued"),
                    "message": "Your merge has been queued and is processing in the background.",

                    "download_available": False,
                    "download_url": None,

                    "total_polygons": 0,
                    "total_files": len(files),
                    "tol_m": tol_m,
                    "corridor_width_m": corridor_width_m,
                    "output_polygons": None,
                    "merged_polygons": None,
                    "input_area_m2": None,
                    "input_area_ha": None,
                    "output_area_m2": None,
                    "output_area_ha": None,

                    "plan": plan,
                    "week": week_key,
                    "weekly_used": None,
                    "free_monthly_credits": free_left,
                    "prepaid_credits": prepaid_left,
                    "credits_used_total": credits_used_total,

                    "files_report": [],
                    "input_preview_geojson": None,
                    "preview_geojson": None,
                    "total_markers": 0,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            return Response(
                {"detail": str(e) or "Failed to queue merge job.", "code": "MERGE_QUEUE_FAILED"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class KMLDownloadView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None

        job = (
            KMLMergeJob.objects
            .filter(id=job_id)
            .filter(Q(user=request.user) | (Q(anon_id=anon_id) if anon_id else Q(pk=None)))
            .first()
        )

        if not job:
            raise NotFound("Não encontrado.")
    
        if job.status in (
            getattr(KMLMergeJob, "STATUS_QUEUED", "queued"),
            getattr(KMLMergeJob, "STATUS_PROCESSING", "processing"),
        ):
            return Response(
                {
                    "detail": "Your merge is still processing.",
                    "code": "JOB_NOT_READY",
                    "status": job.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if job.status == getattr(KMLMergeJob, "STATUS_ERROR", "error"):
            return Response(
                {
                    "detail": "This merge failed and cannot be downloaded.",
                    "code": "JOB_FAILED",
                    "status": job.status,
                    "error_message": getattr(job, "error_message", None) or (job.metrics or {}).get("error_message"),
                },
                status=status.HTTP_409_CONFLICT,
            )
        # ✅ opcional (recomendado): “claim” no primeiro download
        if job.user_id is None:
            job.user = request.user
            job.save(update_fields=["user"])

        bp = ensure_billing_profile(request.user, request=request)
        if not bp:
            return Response(
                {
                    "detail": "BillingProfile ausente.",
                    "code": "BILLING_PROFILE_MISSING",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


        consumed = False
        prepaid_after = None
        should_queue_download_email = False
        now = timezone.now()

        with transaction.atomic():
            job = KMLMergeJob.objects.select_for_update().get(pk=job.pk)
            bp = BillingProfile.objects.select_for_update().get(pk=bp.pk)

            # Recalcula dentro da transação, usando o bp travado
            plan = (bp.plan or "free").lower().strip()
            is_unlimited = bool(getattr(bp, "is_unlimited", False)) or plan in ("pro_monthly", "pro_yearly")

            # Se o job ainda não foi liberado para download, libera agora
            if not bool(getattr(job, "download_unlocked", False)):

                # Plano recorrente/pro: libera sem consumir crédito
                if is_unlimited:
                    job.download_unlocked = True
                    job.download_unlocked_at = now
                    job.download_unlock_source = plan or "pro"

                # Free/prepaid: precisa consumir 1 crédito prepaid
                else:
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

                    job.download_unlocked = True
                    job.download_unlocked_at = now
                    job.download_unlock_source = "prepaid_credit"
                    job.download_credit_consumed = True

                    consumed = True
                    prepaid_after = int(bp.prepaid_credits or 0)

            # Registra uso do download/re-download
            if not job.first_downloaded_at:
                job.first_downloaded_at = now
                should_queue_download_email = True

            job.last_downloaded_at = now
            job.download_count = int(job.download_count or 0) + 1

            job.save(update_fields=[
                "download_unlocked",
                "download_unlocked_at",
                "download_unlock_source",
                "download_credit_consumed",
                "download_count",
                "first_downloaded_at",
                "last_downloaded_at",
            ])

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

        if should_queue_download_email and to_email and has_inputs and has_meta and has_output:
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

        bp = ensure_billing_profile(request.user, request=request)
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
        try:
            if bp.plan == "free":
                bp.reset_free_monthly_if_needed(monthly_amount=FREE_MONTHLY_CREDITS)
                bp.refresh_from_db()
        except Exception as e:
            print("[USAGE] reset_free_monthly_if_needed failed:", e)
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

            # PREPAID (single / pack_5 / futuros packs)
            if mode == "payment" and kind.startswith("prepaid_"):
                metadata = obj.get("metadata") or {}

                # 1️⃣ tenta pegar credits direto da metadata (preferido)
                credits_from_meta = metadata.get("credits")

                try:
                    credits_to_add = int(credits_from_meta)
                except (TypeError, ValueError):
                    credits_to_add = 0

                # 2️⃣ fallback defensivo (caso metadata falhe)
                if credits_to_add <= 0:
                    if kind == "prepaid_1":
                        credits_to_add = PREPAID_SINGLE_CREDIT
                    elif kind == "prepaid_5":
                        credits_to_add = PREPAID_CREDITS_PER_PACK
                    else:
                        print("[stripe] invalid prepaid kind:", kind)
                        return HttpResponse(status=200)

                print(
                    "[stripe] prepaid purchase:",
                    "kind:", kind,
                    "credits:", credits_to_add,
                    "bp_id:", bp.id
                )

                with transaction.atomic():
                    bp = BillingProfile.objects.select_for_update().get(pk=bp.pk)

                    bp.prepaid_credits += credits_to_add

                    # só muda para prepaid se não for pro ilimitado
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


class CheckoutSessionView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        session_id = (request.query_params.get("session_id") or "").strip()

        if not session_id:
            return Response(
                {
                    "detail": "session_id ausente.",
                    "code": "SESSION_ID_MISSING",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.StripeError as e:
            msg = getattr(e, "user_message", None) or str(e)
            return Response(
                {
                    "detail": msg,
                    "code": "STRIPE_SESSION_RETRIEVE_ERROR",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        bp = getattr(request.user, "billing", None)
        customer_id = session.get("customer")

        # Segurança: se o BillingProfile já tem customer_id,
        # garante que a sessão pertence ao usuário autenticado.
        if bp and bp.stripe_customer_id and customer_id:
            if bp.stripe_customer_id != customer_id:
                return Response(
                    {
                        "detail": "Sessão não pertence ao usuário autenticado.",
                        "code": "SESSION_CUSTOMER_MISMATCH",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        payment_status = (session.get("payment_status") or "").lower().strip()
        stripe_status = (session.get("status") or "").lower().strip()
        mode = (session.get("mode") or "").lower().strip()

        metadata = session.get("metadata") or {}

        amount_total = session.get("amount_total") or 0
        currency = (session.get("currency") or "usd").upper()
        value = float(amount_total or 0) / 100

        kind = (metadata.get("kind") or "").lower().strip()
        pack = (metadata.get("pack") or "").lower().strip()
        credits_raw = metadata.get("credits")

        is_paid = payment_status == "paid" or stripe_status == "complete"

        if not is_paid:
            return Response(
                {
                    "detail": "Pagamento ainda não confirmado.",
                    "code": "PAYMENT_NOT_CONFIRMED",
                    "session_id": session_id,
                    "stripe_status": stripe_status,
                    "payment_status": payment_status,
                    "mode": mode,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if kind.startswith("prepaid_"):
            plan_type = kind
        elif mode == "subscription":
            plan_type = "subscription"
        else:
            plan_type = mode or "stripe_checkout"

        try:
            credits = int(credits_raw) if credits_raw is not None else None
        except (TypeError, ValueError):
            credits = None

        return Response(
            {
                "message": "Pagamento confirmado. Seu plano foi atualizado.",
                "session_id": session_id,
                "transaction_id": session_id,

                "payment_status": payment_status,
                "stripe_status": stripe_status,
                "mode": mode,

                # Dados para GA4 / Google Ads
                "value": value,
                "currency": currency,
                "plan_type": plan_type,

                # Extras úteis para debug
                "kind": kind,
                "pack": pack,
                "credits": credits,
            },
            status=status.HTTP_200_OK,
        )

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
            msg = getattr(e, "user_message", None) or str(e)
            return Response(
                {"detail": msg, "code": "STRIPE_PORTAL_ERROR"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"url": portal_session["url"]}, status=status.HTTP_200_OK)

import os
import stripe
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

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

        pack = (request.data.get("pack") or "pack_5").strip()

        # ✅ packs suportados
        if pack == "single":
            price_id = os.getenv("STRIPE_PRICE_ID_SINGLE_1")
            kind = "prepaid_1"
            credits = 1
        elif pack == "pack_5":
            price_id = os.getenv("STRIPE_PRICE_ID_PREPAID_5")
            kind = "prepaid_5"
            credits = 5
        else:
            return Response(
                {"detail": "Pack inválido.", "code": "INVALID_PACK", "pack": pack},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not price_id:
            return Response(
                {"detail": "Stripe price_id não configurado.", "code": "STRIPE_PRICE_ID_MISSING", "pack": pack},
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
                "kind": kind,                  # ✅ prepaid_1 | prepaid_5
                "credits": str(credits),       # ✅ pra webhook/fulfillment
                "pack": pack,                  # ✅ single | pack_5
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
        if status_ in ("queued", "processing", "success", "error"):
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
                "job_id": str(job.id),
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
                "download_available": bool(url),
                "input_filenames": job.input_filenames,

                "preview_geojson": (job.metrics or {}).get("preview_geojson"),
                "input_preview_geojson": (job.metrics or {}).get("input_preview_geojson"),
                "files_report": (job.metrics or {}).get("files_report", []),
                "total_markers": (job.metrics or {}).get("total_markers", 0),
                "error_message": getattr(job, "error_message", None) or (job.metrics or {}).get("error_message"),
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


class KMLAccountPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


def _account_plan_flags(bp):
    plan = (getattr(bp, "plan", None) or "free").lower().strip()
    prepaid_credits = int(getattr(bp, "prepaid_credits", 0) or 0)

    is_unlimited = bool(getattr(bp, "is_unlimited", False)) or plan in (
        "pro_monthly",
        "pro_yearly",
    )

    # Prepaid é cliente pagante e deve acessar histórico/mapas,
    # mesmo se no momento estiver com 0 créditos.
    is_prepaid_customer = plan == "prepaid" or prepaid_credits > 0

    has_full_history_access = bool(is_unlimited or is_prepaid_customer)

    return {
        "plan": plan,
        "is_unlimited": is_unlimited,
        "is_prepaid_customer": is_prepaid_customer,
        "has_full_history_access": has_full_history_access,
        "prepaid_credits": prepaid_credits,
    }


def _plan_label(plan):
    labels = {
        "free": "Free",
        "prepaid": "Prepaid",
        "pro_monthly": "Pro Monthly",
        "pro_yearly": "Pro Yearly",
        "pro": "Pro",
        "anonymous": "Anonymous",
    }
    return labels.get((plan or "").lower().strip(), plan or "Free")


def _merge_mode_from_job(job):
    metrics = job.metrics or {}
    mode = (metrics.get("merge_mode") or "").strip()
    if mode:
        return mode
    return "union"


def _job_can_open_detail(job, flags):
    if bool(getattr(job, "download_unlocked", False)):
        return True
    return bool(flags["has_full_history_access"])


def _job_can_download(job, flags):
    if job.status != getattr(KMLMergeJob, "STATUS_SUCCESS", "success"):
        return False

    if bool(getattr(job, "download_unlocked", False)):
        return True

    if bool(flags["is_unlimited"]):
        return True

    # Se tem crédito, pode tentar baixar; a rota segura vai consumir e liberar.
    if int(flags["prepaid_credits"] or 0) > 0:
        return True

    return False


def _serialize_account_job_list_item(job, flags):
    can_open_detail = _job_can_open_detail(job, flags)
    can_download = _job_can_download(job, flags)

    input_filenames = job.input_filenames or []
    if not isinstance(input_filenames, list):
        input_filenames = []

    return {
        "id": str(job.id),
        "job_id": str(job.id),
        "request_id": job.request_id,
        "status": job.status,
        "plan": job.plan,
        "created_at": job.created_at.isoformat() if job.created_at else None,

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

        "input_filenames": input_filenames[:8],
        "input_filenames_count": len(input_filenames),

        "merge_mode": _merge_mode_from_job(job),

        "download_unlocked": bool(getattr(job, "download_unlocked", False)),
        "download_unlock_source": getattr(job, "download_unlock_source", "") or "",
        "download_credit_consumed": bool(getattr(job, "download_credit_consumed", False)),
        "download_count": int(getattr(job, "download_count", 0) or 0),
        "first_downloaded_at": job.first_downloaded_at.isoformat() if getattr(job, "first_downloaded_at", None) else None,
        "last_downloaded_at": job.last_downloaded_at.isoformat() if getattr(job, "last_downloaded_at", None) else None,

        "can_open_detail": can_open_detail,
        "can_download": can_download,
        "locked_reason": None if can_open_detail else "upgrade_required",

        "total_markers": (job.metrics or {}).get("total_markers", 0),
        "error_message": getattr(job, "error_message", None) or (job.metrics or {}).get("error_message"),
    }


class KMLAccountSummaryView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        bp = ensure_billing_profile(request.user, request=request)

        if not bp:
            return Response(
                {
                    "email": request.user.email,
                    "plan": "free",
                    "plan_label": "Free",
                    "access_level": "limited",
                    "history_locked": True,
                    "can_access_history": False,
                    "can_access_maps": False,
                    "can_download_from_history": False,

                    "prepaid_credits": 0,
                    "free_monthly_credits": 0,
                    "credits_used_total": 0,
                    "current_period_end": None,
                    "cancel_at_period_end": False,

                    "total_jobs": 0,
                    "success_jobs": 0,
                    "error_jobs": 0,
                    "processing_jobs": 0,
                    "queued_jobs": 0,
                    "unlocked_jobs": 0,
                    "total_files": 0,
                    "total_input_area_ha": 0,
                    "total_output_area_ha": 0,
                    "last_merge_at": None,
                },
                status=status.HTTP_200_OK,
            )

        flags = _account_plan_flags(bp)

        base_qs = KMLMergeJob.objects.filter(user=request.user)

        total_jobs = base_qs.count()
        success_jobs = base_qs.filter(status=KMLMergeJob.STATUS_SUCCESS).count()
        error_jobs = base_qs.filter(status=KMLMergeJob.STATUS_ERROR).count()
        processing_jobs = base_qs.filter(status=KMLMergeJob.STATUS_PROCESSING).count()
        queued_jobs = base_qs.filter(status=KMLMergeJob.STATUS_QUEUED).count()
        unlocked_jobs = base_qs.filter(download_unlocked=True).count()

        agg = base_qs.aggregate(
            total_files_sum=Sum("total_files"),
            total_input_area_ha_sum=Sum("input_area_ha"),
            total_output_area_ha_sum=Sum("output_area_ha"),
        )

        last_merge = base_qs.order_by("-created_at").first()

        history_locked = not flags["has_full_history_access"]

        return Response(
            {
                "email": request.user.email,
                "plan": flags["plan"],
                "plan_label": _plan_label(flags["plan"]),
                "access_level": "full" if flags["has_full_history_access"] else "limited",
                "history_locked": history_locked,
                "can_access_history": flags["has_full_history_access"],
                "can_access_maps": flags["has_full_history_access"],
                "can_download_from_history": bool(flags["is_unlimited"] or flags["prepaid_credits"] > 0),

                "prepaid_credits": int(bp.prepaid_credits or 0),
                "free_monthly_credits": int(bp.free_monthly_credits or 0),
                "credits_used_total": int(bp.credits_used_total or 0),
                "current_period_end": bp.current_period_end.isoformat() if bp.current_period_end else None,
                "cancel_at_period_end": bool(bp.cancel_at_period_end),

                "total_jobs": total_jobs,
                "success_jobs": success_jobs,
                "error_jobs": error_jobs,
                "processing_jobs": processing_jobs,
                "queued_jobs": queued_jobs,
                "unlocked_jobs": unlocked_jobs,
                "total_files": int(agg.get("total_files_sum") or 0),
                "total_input_area_ha": float(agg.get("total_input_area_ha_sum") or 0),
                "total_output_area_ha": float(agg.get("total_output_area_ha_sum") or 0),
                "last_merge_at": last_merge.created_at.isoformat() if last_merge else None,

                "upgrade_cta": (
                    "Upgrade to access previous maps, details, and downloads whenever you need them."
                    if history_locked
                    else ""
                ),
            },
            status=status.HTTP_200_OK,
        )


class KMLAccountJobsView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        bp = ensure_billing_profile(request.user, request=request)
        flags = _account_plan_flags(bp) if bp else {
            "plan": "free",
            "is_unlimited": False,
            "is_prepaid_customer": False,
            "has_full_history_access": False,
            "prepaid_credits": 0,
        }

        qs = (
            KMLMergeJob.objects
            .filter(user=request.user)
            .only(
                "id",
                "request_id",
                "status",
                "plan",
                "created_at",
                "total_files",
                "total_polygons",
                "tol_m",
                "corridor_width_m",
                "output_polygons",
                "merged_polygons",
                "input_area_m2",
                "input_area_ha",
                "output_area_m2",
                "output_area_ha",
                "input_filenames",
                "metrics",
                "download_unlocked",
                "download_unlocked_at",
                "download_unlock_source",
                "download_credit_consumed",
                "download_count",
                "first_downloaded_at",
                "last_downloaded_at",
            )
            .order_by("-created_at")
        )

        status_ = (request.query_params.get("status") or "").strip().lower()
        if status_ in ("queued", "processing", "success", "error"):
            qs = qs.filter(status=status_)

        unlocked = (request.query_params.get("unlocked") or "").strip().lower()
        if unlocked in ("1", "true", "yes"):
            qs = qs.filter(download_unlocked=True)
        elif unlocked in ("0", "false", "no"):
            qs = qs.filter(download_unlocked=False)

        paginator = KMLAccountPagination()
        page = paginator.paginate_queryset(qs, request)

        items = [_serialize_account_job_list_item(job, flags) for job in page]

        response = paginator.get_paginated_response(items)
        response.data["plan"] = flags["plan"]
        response.data["access_level"] = "full" if flags["has_full_history_access"] else "limited"
        response.data["history_locked"] = not flags["has_full_history_access"]
        response.data["prepaid_credits"] = flags["prepaid_credits"]
        return response


class KMLAccountJobDetailView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request, job_id):
        bp = ensure_billing_profile(request.user, request=request)
        flags = _account_plan_flags(bp) if bp else {
            "plan": "free",
            "is_unlimited": False,
            "is_prepaid_customer": False,
            "has_full_history_access": False,
            "prepaid_credits": 0,
        }

        job = get_object_or_404(KMLMergeJob, id=job_id, user=request.user)

        can_open_detail = _job_can_open_detail(job, flags)

        if not can_open_detail:
            return Response(
                {
                    "detail": "Upgrade required to access merge details.",
                    "code": "HISTORY_DETAIL_LOCKED",
                    "job_id": str(job.id),
                    "download_unlocked": bool(job.download_unlocked),
                    "can_open_detail": False,
                    "can_download": _job_can_download(job, flags),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        item = _serialize_account_job_list_item(job, flags)

        metrics = job.metrics or {}

        item.update({
            "preview_geojson": metrics.get("preview_geojson"),
            "input_preview_geojson": metrics.get("input_preview_geojson"),
            "files_report": metrics.get("files_report", []),
            "metrics": {
                k: v
                for k, v in metrics.items()
                if k not in ("preview_geojson", "input_preview_geojson", "files_report")
            },
        })

        return Response(item, status=status.HTTP_200_OK)


class ProfileOnboardingView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def patch(self, request):
        bp = ensure_billing_profile(request.user)
        if not bp:
            return Response({"detail": "BillingProfile ausente."}, status=status.HTTP_401_UNAUTHORIZED)

        use_case = (request.data.get("use_case") or "").strip()
        usage_frequency = (request.data.get("usage_frequency") or "").strip()
        skipped = bool(request.data.get("skipped") or False)

        allowed_use_case = {k for k, _ in BillingProfile.USE_CASE_CHOICES}
        allowed_freq = {k for k, _ in BillingProfile.USAGE_FREQUENCY_CHOICES}

        update_fields = ["updated_at"]

        if skipped:
            bp.onboarding_skipped_count = int(bp.onboarding_skipped_count or 0) + 1
            update_fields.append("onboarding_skipped_count")
        else:
            if use_case and use_case not in allowed_use_case:
                return Response({"detail": "Invalid use_case.", "code": "INVALID_USE_CASE"}, status=400)
            if usage_frequency and usage_frequency not in allowed_freq:
                return Response({"detail": "Invalid usage_frequency.", "code": "INVALID_USAGE_FREQUENCY"}, status=400)

            # grava só se vier preenchido (e normalmente você manda os dois)
            if use_case:
                bp.use_case = use_case
                update_fields.append("use_case")
            if usage_frequency:
                bp.usage_frequency = usage_frequency
                update_fields.append("usage_frequency")

            # marca como concluído quando ambos foram informados
            if bp.use_case and bp.usage_frequency and not bp.onboarding_completed_at:
                bp.onboarding_completed_at = timezone.now()
                update_fields.append("onboarding_completed_at")

        bp.save(update_fields=update_fields)

        return Response(
            {
                "use_case": bp.use_case or "",
                "usage_frequency": bp.usage_frequency or "",
                "onboarding_completed_at": bp.onboarding_completed_at.isoformat() if bp.onboarding_completed_at else None,
                "onboarding_skipped_count": int(bp.onboarding_skipped_count or 0),
            },
            status=200,
        )




class ClaimJobsView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        anon_id = (request.headers.get("X-ANON-ID") or "").strip()
        if not anon_id:
            return Response({"detail": "Missing X-ANON-ID."}, status=400)

        updated = KMLMergeJob.objects.filter(user__isnull=True, anon_id=anon_id).update(user=request.user)
        return Response({"claimed": updated}, status=200)



class UnlockFreeCreditView(APIView):
    """
    Salva o formulário de unlock e concede 1 crédito (prepaid_credits += 1).
    Requer usuário autenticado, pois crédito vive no BillingProfile.
    """
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        bp = ensure_billing_profile(request.user)
        if not bp:
            return Response(
                {"detail": "BillingProfile ausente."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        plan_now = (getattr(bp, "plan", "") or "free").lower().strip()

        if plan_now != "free":
            return Response(
                {
                    "detail": "Free unlock is only available for free accounts.",
                    "code": "FREE_UNLOCK_ONLY_FOR_FREE_PLAN",
                    "plan": plan_now,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None
        ip_address = get_client_ip(request)

        # opcional: ignora IPs privados / inválidos
        if ip_address and not is_public_ip(ip_address):
            ip_address = None

        # anti-abuso por conta
        if bool(getattr(bp, "free_unlock_used", False)):
            return Response(
                {
                    "detail": "Free unlock already used.",
                    "code": "FREE_UNLOCK_ALREADY_USED",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # anti-abuso por dispositivo/navegador
        if anon_id and UnlockFeedback.objects.filter(anon_id=anon_id).exists():
            return Response(
                {
                    "detail": "Free unlock already used on this device.",
                    "code": "FREE_UNLOCK_ALREADY_USED_FOR_DEVICE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # anti-abuso por IP/rede
        if ip_address and UnlockFeedback.objects.filter(ip_address=ip_address).exists():
            return Response(
                {
                    "detail": "Free unlock already used from this network.",
                    "code": "FREE_UNLOCK_ALREADY_USED_FOR_IP",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # payload
        use_case = (request.data.get("use_case") or "").strip()
        frequency = (request.data.get("frequency") or "").strip()
        willingness = (request.data.get("willingness") or "").strip()
        price_expectation = (request.data.get("price_expectation") or "").strip()
        other_use_case_text = (request.data.get("other_use_case_text") or "").strip()

        missing = []
        if not use_case:
            missing.append("use_case")
        if not frequency:
            missing.append("frequency")
        if not willingness:
            missing.append("willingness")
        if willingness != "no" and not price_expectation:
            missing.append("price_expectation")

        if willingness == "no":
            price_expectation = ""

        if use_case == "other" and len(other_use_case_text) < 3:
            return Response(
                {
                    "detail": "Missing fields.",
                    "missing": ["other_use_case_text"],
                    "code": "MISSING_FIELDS",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if use_case != "other":
            other_use_case_text = ""

        if missing:
            return Response(
                {
                    "detail": "Missing fields.",
                    "missing": missing,
                    "code": "MISSING_FIELDS",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            bp = BillingProfile.objects.select_for_update().get(pk=bp.pk)
            
            # ✅ recheck transacional: se virou prepaid/pro no meio do caminho, bloqueia
            plan_now = (getattr(bp, "plan", "") or "free").lower().strip()

            if plan_now != "free":
                return Response(
                    {
                        "detail": "Free unlock is only available for free accounts.",
                        "code": "FREE_UNLOCK_ONLY_FOR_FREE_PLAN",
                        "plan": plan_now,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # recheck por conta
            if bool(getattr(bp, "free_unlock_used", False)):
                return Response(
                    {
                        "detail": "Free unlock already used.",
                        "code": "FREE_UNLOCK_ALREADY_USED",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # recheck por dispositivo
            if anon_id and UnlockFeedback.objects.select_for_update().filter(anon_id=anon_id).exists():
                return Response(
                    {
                        "detail": "Free unlock already used on this device.",
                        "code": "FREE_UNLOCK_ALREADY_USED_FOR_DEVICE",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # recheck por IP
            if ip_address and UnlockFeedback.objects.select_for_update().filter(ip_address=ip_address).exists():
                return Response(
                    {
                        "detail": "Free unlock already used from this network.",
                        "code": "FREE_UNLOCK_ALREADY_USED_FOR_IP",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            UnlockFeedback.objects.create(
                user=request.user,
                anon_id=anon_id,
                ip_address=ip_address,
                use_case=use_case,
                frequency=frequency,
                willingness=willingness,
                price_expectation=price_expectation,
                other_use_case_text=other_use_case_text,
            )

            bp.prepaid_credits = int(getattr(bp, "prepaid_credits", 0) or 0) + 1
            bp.free_unlock_used = True
            bp.save(update_fields=["prepaid_credits", "free_unlock_used", "updated_at"])

        return Response(
            {
                "credit_granted": True,
                "prepaid_credits": int(bp.prepaid_credits or 0),
                "free_unlock_used": True,
            },
            status=status.HTTP_200_OK,
        )
        


class SendTestReactivationEmailView(View):
    def get(self, request, *args, **kwargs):
        test_email = getattr(settings, "KML_TEST_EMAIL", None) or "patamarcelo@gmail.com"

        result = send_reactivation_email(
            to=test_email,
        )

        return JsonResponse({
            "ok": True,
            "sent_to": test_email,
            "result": result,
        })
        

class KMLJobStatusView(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (AllowAny,)

    def get(self, request, job_id):
        anon_id = (request.headers.get("X-ANON-ID") or "").strip() or None
        user = request.user if getattr(request.user, "is_authenticated", False) else None

        is_recovery = (request.query_params.get("recover") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        job = KMLMergeJob.objects.filter(id=job_id).first()

        if not job:
            raise NotFound("Not found.")

        # ------------------------------------------------------------
        # ACCESS RULES
        # ------------------------------------------------------------
        #
        # Fluxo normal:
        # - usuário logado acessa se job.user == request.user
        # - ou se o anon_id do navegador é o mesmo do job
        #
        # Fluxo recovery:
        # - se deslogado e job tem user vinculado, retorna 401 claro
        #   para o front abrir login e tentar de novo depois.
        #
        # Importante:
        # - Não abrimos preview público só por UUID.
        # - Não quebramos o fluxo antigo, porque anon_id continua funcionando.
        # ------------------------------------------------------------

        if user:
            can_access = False

            if job.user_id and job.user_id == user.id:
                can_access = True

            if anon_id and job.anon_id and job.anon_id == anon_id:
                can_access = True

            # Se o job foi criado anônimo e o mesmo navegador agora está logado,
            # vincula ao usuário automaticamente.
            if can_access and job.user_id is None:
                job.user = user
                job.save(update_fields=["user"])

            if not can_access:
                raise NotFound("Not found.")

        else:
            # Recovery por e-mail: se o job já pertence a um usuário,
            # peça login em vez de responder 404 genérico.
            if is_recovery and job.user_id:
                return Response(
                    {
                        "detail": "Sign in to open this result.",
                        "code": "AUTH_REQUIRED_FOR_RECOVERY",
                        "job_id": str(job.id),
                        "status": job.status,
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Fluxo anônimo antigo: mantém exatamente a regra por anon_id.
            if not anon_id or not job.anon_id or job.anon_id != anon_id:
                raise NotFound("Not found.")

        try:
            url = default_storage.url(job.storage_path) if job.storage_path else None
        except Exception:
            url = None

        metrics = job.metrics or {}

        return Response(
            {
                "id": str(job.id),
                "job_id": str(job.id),
                "request_id": job.request_id,
                "status": job.status,
                "plan": job.plan,
                "created_at": job.created_at.isoformat() if job.created_at else None,

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

                # Linhas / CAD
                "geometry_type": metrics.get("geometry_type"),
                "line_merge_mode": metrics.get("merge_mode"),
                "input_lines": metrics.get("input_lines"),
                "output_lines": metrics.get("output_lines"),
                "bridges_created": metrics.get("bridges_created"),
                "input_length_m": metrics.get("input_length_m"),
                "input_length_km": metrics.get("input_length_km"),
                "output_length_m": metrics.get("output_length_m"),
                "output_length_km": metrics.get("output_length_km"),
                "total_cad_lines": metrics.get("total_cad_lines", 0),
                "bridge_reports": metrics.get("bridge_reports", []),

                # Download
                "download_url": url,
                "download_available": bool(url),

                # Arquivos
                "input_filenames": job.input_filenames,

                # Preview do mapa
                "preview_geojson": metrics.get("preview_geojson"),
                "input_preview_geojson": metrics.get("input_preview_geojson"),

                # Debug/relatórios
                "files_report": metrics.get("files_report", []),
                "total_markers": metrics.get("total_markers", 0),
                "error_message": getattr(job, "error_message", None) or metrics.get("error_message"),

                # Estado de liberação/download
                "download_unlocked": bool(getattr(job, "download_unlocked", False)),
                "download_unlock_source": getattr(job, "download_unlock_source", "") or "",
                "download_credit_consumed": bool(getattr(job, "download_credit_consumed", False)),
                "download_count": int(getattr(job, "download_count", 0) or 0),
                "first_downloaded_at": (
                    job.first_downloaded_at.isoformat()
                    if getattr(job, "first_downloaded_at", None)
                    else None
                ),
                "last_downloaded_at": (
                    job.last_downloaded_at.isoformat()
                    if getattr(job, "last_downloaded_at", None)
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )
        
    
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import KMLMergeJob


class PublicKMLStatsView(APIView):
    """
    Public social-proof stats for KML Unifier landing.

    Returns only aggregated, non-sensitive metrics.
    No emails, anon IDs, IPs, job IDs or user data.
    """

    authentication_classes = []
    permission_classes = []

    CACHE_KEY = "kmltools:public_kml_stats:v2"
    CACHE_TIMEOUT = 60 * 30  # 30 minutes

    def _number(self, value):
        if value is None:
            return 0

        if isinstance(value, Decimal):
            return float(value)

        return value

    def get(self, request, *args, **kwargs):
        cached = cache.get(self.CACHE_KEY)
        if cached:
            return Response(cached)

        successful_jobs = KMLMergeJob.objects.filter(
            status=KMLMergeJob.STATUS_SUCCESS
        )

        agg = successful_jobs.aggregate(
            total_polygons_processed=Sum("total_polygons"),
            total_files_processed=Sum("total_files"),
            total_input_area_ha=Sum("input_area_ha"),
            total_output_area_ha=Sum("output_area_ha"),
        )

        total_polygons_processed = int(self._number(agg.get("total_polygons_processed")) or 0)
        total_files_processed = int(self._number(agg.get("total_files_processed")) or 0)

        # Preferência:
        # 1. input_area_ha = área real recebida/processada
        # 2. output_area_ha = fallback se input_area_ha estiver zerado
        input_area_ha = float(self._number(agg.get("total_input_area_ha")) or 0)
        output_area_ha = float(self._number(agg.get("total_output_area_ha")) or 0)

        total_area_ha = input_area_ha if input_area_ha > 0 else output_area_ha

        total_countries = (
            successful_jobs
            .exclude(visitor_country__isnull=True)
            .exclude(visitor_country="")
            .values("visitor_country")
            .distinct()
            .count()
        )

        data = {
            "total_polygons_processed": total_polygons_processed,
            "total_files_processed": total_files_processed,
            "total_countries": total_countries,
            "total_area_ha": int(total_area_ha),
        }
        print('data ', data)
        cache.set(self.CACHE_KEY, data, self.CACHE_TIMEOUT)

        return Response(data)