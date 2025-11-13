# core/geo_merge.py
from __future__ import annotations
from typing import List, Dict, Tuple
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union, transform as shp_transform, nearest_points
from shapely.geometry.base import BaseGeometry
from pyproj import CRS, Transformer, Geod
from xml.dom.minidom import Document
import math
from math import isclose


GEOD = Geod(ellps="WGS84")

def geodesic_area_m2(geom_ll: Polygon | MultiPolygon) -> float:
    """
    Calcula área geodésica em m² (como o Google Earth faz).
    geom_ll deve estar em lon/lat (EPSG:4326).
    """
    def area_poly(p: Polygon) -> float:
        # exterior
        lons, lats = zip(*list(p.exterior.coords))
        area_ext, _ = GEOD.polygon_area_perimeter(lons, lats)

        # interiores (buracos)
        area_holes = 0.0
        for ring in p.interiors:
            h_lons, h_lats = zip(*list(ring.coords))
            a_hole, _ = GEOD.polygon_area_perimeter(h_lons, h_lats)
            area_holes += a_hole  # também vem negativa

        # área vem negativa (orientação CCW) → usa abs
        return abs(area_ext) - abs(area_holes)

    if isinstance(geom_ll, Polygon):
        return area_poly(geom_ll)
    elif isinstance(geom_ll, MultiPolygon):
        return sum(area_poly(p) for p in geom_ll.geoms)
    else:
        return 0.0
    
    
# ---------- Helpers de projeção ----------
def choose_utm_epsg(polys_ll: List[Polygon]) -> int:
    all_lons = [x for p in polys_ll for (x, y) in p.exterior.coords]
    all_lats = [y for p in polys_ll for (x, y) in p.exterior.coords]
    center_lon = sum(all_lons) / len(all_lons)
    center_lat = sum(all_lats) / len(all_lats)
    zone = int(math.floor((center_lon + 180) / 6) + 1)
    south = center_lat < 0
    return 32700 + zone if south else 32600 + zone

def to_polygons_ll(parcelas: List[Dict]) -> Tuple[List[Polygon], List[str]]:
    """
    Espera cada parcela com:
      {
        "talhao": "B12",
        "coords": [{"latitude": -10.66, "longitude": -49.83}, ...]  # anel exterior (fechado ou não)
      }
    """
    polys, names = [], []

    for parc in parcelas:
        nome = (parc.get("talhao") or "Sem nome").strip()
        coords = parc.get("coords") or []

        # (lon, lat) para shapely + remove duplicatas consecutivas
        ring = []
        last = None
        for p in coords:
            if "longitude" in p and "latitude" in p:
                pt = (float(p["longitude"]), float(p["latitude"]))
                if last is None or pt != last:
                    ring.append(pt)
                    last = pt

        # precisa de ao menos 3 pontos distintos (fechamento vira 4)
        if len(ring) < 3:
            continue

        # garante fechamento do anel
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        poly = Polygon(ring)
        if poly.is_empty or poly.area <= 0:
            continue

        # correção leve se inválido
        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty or poly.area <= 0:
                continue

        # pode vir MultiPolygon depois do buffer(0); mantenha união das partes > 0
        if isinstance(poly, MultiPolygon):
            parts = [p for p in poly.geoms if (not p.is_empty and p.area > 0)]
            if not parts:
                continue
            poly = unary_union(parts)

        if poly.is_empty or poly.area <= 0:
            continue

        polys.append(poly)
        names.append(nome)

    return polys, names

def polygon_parts(g: BaseGeometry) -> List[Polygon]:
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    # GeometryCollection -> só polígonos
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]

# ---------- Agrupamento por proximidade ----------
def build_groups_by_proximity(polys_ll: List[Polygon], tol_m: float, epsg: int):
    src = CRS.from_epsg(4326); dst = CRS.from_epsg(epsg)
    to_utm = Transformer.from_crs(src, dst, always_xy=True).transform
    to_ll = Transformer.from_crs(dst, src, always_xy=True).transform

    polys_utm = [shp_transform(to_utm, p) for p in polys_ll]

    n = len(polys_utm)
    parent = list(range(n))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def union(a,b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    bboxes = [p.bounds for p in polys_utm]
    def bbox_pad(b, pad):
        minx, miny, maxx, maxy = b
        return (minx-pad, miny-pad, maxx+pad, maxy+pad)
    def bbox_intersects(b1, b2):
        minx1, miny1, maxx1, maxy1 = b1
        minx2, miny2, maxx2, maxy2 = b2
        return not (maxx2 < minx1 or maxx1 < minx2 or maxy2 < miny1 or maxy1 < miny2)

    for i in range(n):
        for j in range(i+1, n):
            if not bbox_intersects(bbox_pad(bboxes[i], tol_m), bbox_pad(bboxes[j], tol_m)):
                continue
            if polys_utm[i].distance(polys_utm[j]) <= tol_m:
                union(i, j)

    groups = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)
    return groups, polys_utm, to_ll

# ---------- MST + corredores finos ----------
def mst_edges(parts: List[Polygon], tol_m: float):
    m = len(parts)
    if m <= 1: return []
    edges = []
    for i in range(m):
        for j in range(i+1, m):
            d = parts[i].distance(parts[j])
            if d <= tol_m:
                edges.append((d, i, j))
    edges.sort(key=lambda x: x[0])
    if not edges:
        return []
    in_tree = {0}
    remaining = set(range(1, m))
    chosen = []
    while remaining:
        best = None
        for d, i, j in edges:
            if (i in in_tree and j in remaining) or (j in in_tree and i in remaining):
                best = (i, j)
                break
        if best is None:
            break
        i, j = best
        chosen.append((i, j))
        if i in in_tree:
            in_tree.add(j); remaining.discard(j)
        else:
            in_tree.add(i); remaining.discard(i)
    return chosen

# ---------- Núcleo “híbrido no-flood” ----------
def merge_no_flood(parcelas: List[Dict], tol_m: float = 20.0, corridor_width_m: float = 1.0,
                   style_color: str = "60FFFFFF",  return_metrics: bool = False) -> str:
    """
    Retorna o KML como string.
    Estratégia:
      BASE = union(originais + corredores_finos)
      SHELL = union( buffer(tol) ) buffer(-tol)
      FINAL = BASE ∪ (SHELL ∩ máscara_corredor)
      => Preserva 'buracos', só amplia nas áreas estritamente necessárias (corredores).
    """
    polys_ll, names = to_polygons_ll(parcelas)
    if not polys_ll:
        raise ValueError("Nenhuma parcela válida recebida.")

    epsg = choose_utm_epsg(polys_ll)
    groups, polys_utm, to_ll = build_groups_by_proximity(polys_ll, tol_m, epsg)

    finals_ll, finals_names = [], []
    input_area_m2 = sum(p.area for p in polys_utm)
    input_area_ha = input_area_m2 / 10000.0
    
    finals_utm = []
    total_output_area_m2 = 0.0

    for root_idx, idxs in groups.items():
        originals = [polys_utm[i] for i in idxs]

        # Shell bridged (usada só como envelope)
        SHELL = unary_union([p.buffer(tol_m) for p in originals]).buffer(-tol_m)

        # BASE: originais + corredores finos (MST)
        parts = []
        for g in originals:
            parts.extend(polygon_parts(g))

        corridors = []
        if len(parts) > 1:
            for a, b in mst_edges(parts, tol_m):
                Apt, Bpt = nearest_points(parts[a], parts[b])
                line = LineString([Apt.coords[0], Bpt.coords[0]])
                corridors.append(line.buffer(corridor_width_m / 2.0, cap_style=2, join_style=2))

        BASE = unary_union(parts + corridors)

        # máscara do corredor (um “halo” mínimo p/ evitar micro-falhas de render)
        corridor_mask = unary_union(corridors) if corridors else None
        if corridor_mask:
            # ~60% da largura como halo
            corridor_mask = corridor_mask.buffer(max(0.01, corridor_width_m * 0.6))

        FINAL_utm = BASE.union(SHELL.intersection(corridor_mask)) if corridor_mask else BASE
        FINAL_ll = shp_transform(to_ll, FINAL_utm)
        
        area_out_m2 = geodesic_area_m2(FINAL_ll)
        total_output_area_m2 += area_out_m2

        finals_utm.append(FINAL_utm)  # <-- guarda em UTM (m²)
        finals_ll.append(FINAL_ll)
        finals_names.append(", ".join([names[i] for i in idxs]))

    def _pts_equal(a, b, eps=1e-12):
        return isclose(a[0], b[0], abs_tol=eps) and isclose(a[1], b[1], abs_tol=eps)

    def _clean_ring_for_kml(iterable_coords, eps=1e-12):
        """
        - Remove duplicatas consecutivas (com tolerância)
        - Garante fechamento
        - Retorna lista já pronta p/ KML ([(x,y), ...]) ou [] se degenerado (<3 únicos)
        """
        coords = [(float(x), float(y)) for (x, y) in iterable_coords]

        # 1) remove duplicatas consecutivas
        cleaned = []
        last = None
        for pt in coords:
            if last is None or not _pts_equal(pt, last, eps):
                cleaned.append(pt)
                last = pt

        if not cleaned:
            return []

        # 2) fecha anel se precisar
        if not _pts_equal(cleaned[0], cleaned[-1], eps):
            cleaned.append(cleaned[0])

        # 3) conta únicos (sem considerar o último duplicado do fechamento)
        uniques = []
        for pt in cleaned[:-1]:
            if not uniques or not _pts_equal(pt, uniques[-1], eps):
                uniques.append(pt)

        # KML exige >= 3 coordenadas únicas para formar polígono
        if len(uniques) < 3:
            return []

        # 4) volta a fechar com o primeiro dos "uniques"
        closed = uniques[:]
        if not _pts_equal(closed[0], closed[-1], eps):
            closed.append(closed[0])

        return closed

    def _coords_to_kml_str(coords):
        # coords já limpos/fechados
        return " ".join(f"{x:.8f},{y:.8f}" for (x, y) in coords)
    
    output_area_m2 = 0.0
    merged_polygons = 0

    for g in finals_utm:
        for p in polygon_parts(g):
            output_area_m2 += p.area
            merged_polygons += 1

    output_area_ha = output_area_m2 / 10000.0

    doc = Document()
    kml = doc.createElement("kml"); kml.setAttribute("xmlns", "http://www.opengis.net/kml/2.2")
    doc.appendChild(kml)
    document = doc.createElement("Document"); kml.appendChild(document)

    style = doc.createElement("Style"); style.setAttribute("id", "styleMerged")
    ls = doc.createElement("LineStyle")
    lc = doc.createElement("color"); lc.appendChild(doc.createTextNode("ff000000"))
    lw = doc.createElement("width"); lw.appendChild(doc.createTextNode("2"))
    ls.appendChild(lc); ls.appendChild(lw)
    ps = doc.createElement("PolyStyle")
    pc = doc.createElement("color"); pc.appendChild(doc.createTextNode(style_color))
    ps.appendChild(pc)
    style.appendChild(ls); style.appendChild(ps)
    document.appendChild(style)

    counter = 1
    for idx, geom in enumerate(finals_ll):
        geoms = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        for poly in geoms:
            # ------ outer ring ------
            outer_clean = _clean_ring_for_kml(list(poly.exterior.coords))
            if not outer_clean:
                # Se o outer degradou (ex.: união gerou sliver), pula este poly
                continue

            pm = doc.createElement("Placemark")
            nm = doc.createElement("name"); nm.appendChild(doc.createTextNode(f"Area_{counter}"))
            su = doc.createElement("styleUrl"); su.appendChild(doc.createTextNode("#styleMerged"))
            pm.appendChild(nm); pm.appendChild(su)

            pg = doc.createElement("Polygon")

            # outerBoundaryIs
            obi = doc.createElement("outerBoundaryIs")
            lr = doc.createElement("LinearRing")
            coords_el = doc.createElement("coordinates")
            coords_el.appendChild(doc.createTextNode(_coords_to_kml_str(outer_clean)))
            lr.appendChild(coords_el); obi.appendChild(lr); pg.appendChild(obi)

            # ------ inner rings (buracos) ------
            for interior in poly.interiors:
                inner_clean = _clean_ring_for_kml(list(interior.coords))
                if not inner_clean:
                    # buraco degenerado → ignora (evita erro do Earth)
                    continue
                ibi = doc.createElement("innerBoundaryIs")
                lr_i = doc.createElement("LinearRing")
                coords_i = doc.createElement("coordinates")
                coords_i.appendChild(doc.createTextNode(_coords_to_kml_str(inner_clean)))
                lr_i.appendChild(coords_i); ibi.appendChild(lr_i); pg.appendChild(ibi)

            pm.appendChild(pg)
            document.appendChild(pm)
            counter += 1

    kml_str = doc.toprettyxml(indent="  ")

    if return_metrics:
        metrics = {
            "input_area_m2": float(input_area_m2),
            "input_area_ha": float(input_area_ha),
            "output_area_m2": float(output_area_m2),
            "output_area_ha": float(output_area_ha),
            "merged_polygons": int(merged_polygons),
            "output_area_m2": total_output_area_m2,
            "output_polygons": counter - 1,  # porque começamos counter = 1
        }
        return kml_str, metrics

    return kml_str
