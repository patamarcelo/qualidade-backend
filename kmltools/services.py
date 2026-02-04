# core/geo_merge.py
from __future__ import annotations
from typing import List, Dict, Tuple

import math
from math import isclose

from shapely.geometry import Polygon, MultiPolygon, LineString, GeometryCollection
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union, transform as shp_transform, nearest_points

from pyproj import CRS, Transformer, Geod
from xml.dom.minidom import Document
from shapely.geometry.polygon import orient




GEOD = Geod(ellps="WGS84")


def geodesic_area_m2(geom_ll: Polygon | MultiPolygon) -> float:
    def area_poly(p: Polygon) -> float:
        lons, lats = zip(*list(p.exterior.coords))
        area_ext, _ = GEOD.polygon_area_perimeter(lons, lats)

        area_holes = 0.0
        for ring in p.interiors:
            h_lons, h_lats = zip(*list(ring.coords))
            a_hole, _ = GEOD.polygon_area_perimeter(h_lons, h_lats)
            area_holes += a_hole

        return abs(area_ext) - abs(area_holes)

    if isinstance(geom_ll, Polygon):
        return area_poly(geom_ll)
    if isinstance(geom_ll, MultiPolygon):
        return sum(area_poly(p) for p in geom_ll.geoms)
    return 0.0


def choose_utm_epsg(polys_ll: List[Polygon]) -> int:
    all_lons = [x for p in polys_ll for (x, y) in p.exterior.coords]
    all_lats = [y for p in polys_ll for (x, y) in p.exterior.coords]
    center_lon = sum(all_lons) / len(all_lons)
    center_lat = sum(all_lats) / len(all_lats)
    zone = int(math.floor((center_lon + 180) / 6) + 1)
    south = center_lat < 0
    return 32700 + zone if south else 32600 + zone


def to_polygons_ll(parcelas: List[Dict]) -> Tuple[List[Polygon], List[str]]:
    polys, names = [], []

    for parc in parcelas:
        nome = (parc.get("talhao") or "Sem nome").strip()
        coords = parc.get("coords") or []

        ring = []
        last = None
        for p in coords:
            if "longitude" in p and "latitude" in p:
                pt = (float(p["longitude"]), float(p["latitude"]))
                if last is None or pt != last:
                    ring.append(pt)
                    last = pt

        if len(ring) < 3:
            continue

        if ring[0] != ring[-1]:
            ring.append(ring[0])

        poly = Polygon(ring)
        if poly.is_empty or poly.area <= 0:
            continue

        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty or poly.area <= 0:
                continue

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
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    if isinstance(g, GeometryCollection):
        out = []
        for gg in g.geoms:
            out.extend(polygon_parts(gg))
        return out
    return []


def build_groups_by_proximity(polys_ll: List[Polygon], tol_m: float, epsg: int):
    src = CRS.from_epsg(4326)
    dst = CRS.from_epsg(epsg)
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

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    bboxes = [p.bounds for p in polys_utm]

    def bbox_pad(b, pad):
        minx, miny, maxx, maxy = b
        return (minx - pad, miny - pad, maxx + pad, maxy + pad)

    def bbox_intersects(b1, b2):
        minx1, miny1, maxx1, maxy1 = b1
        minx2, miny2, maxx2, maxy2 = b2
        return not (maxx2 < minx1 or maxx1 < minx2 or maxy2 < miny1 or maxy1 < miny2)

    for i in range(n):
        for j in range(i + 1, n):
            if not bbox_intersects(bbox_pad(bboxes[i], tol_m), bbox_pad(bboxes[j], tol_m)):
                continue
            if polys_utm[i].distance(polys_utm[j]) <= tol_m:
                union(i, j)

    groups = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    return groups, polys_utm, to_ll


def mst_edges(parts: List[Polygon], tol_m: float):
    m = len(parts)
    if m <= 1:
        return []

    edges = []
    for i in range(m):
        for j in range(i + 1, m):
            d = parts[i].distance(parts[j])
            # IMPORTANTE: se d == 0, já há overlap/toque; não precisa corredor (evita degeneração)
            if 0 < d <= tol_m:
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
            in_tree.add(j)
            remaining.discard(j)
        else:
            in_tree.add(i)
            remaining.discard(i)

    return chosen

def merge_no_flood(
    parcelas: List[Dict],
    tol_m: float = 20.0,
    corridor_width_m: float = 1.0,
    style_color: str = "4d00ff00",  # ~30% de opacidade, verde
    return_metrics: bool = False,
) -> str:
    polys_ll, names = to_polygons_ll(parcelas)
    if not polys_ll:
        raise ValueError("Nenhuma parcela válida recebida.")

    epsg = choose_utm_epsg(polys_ll)
    groups, polys_utm, to_ll = build_groups_by_proximity(polys_ll, tol_m, epsg)

    finals_ll, finals_names = [], []
    finals_utm = []

    input_area_m2 = sum(p.area for p in polys_utm)  # UTM: m²
    input_area_ha = input_area_m2 / 10000.0

    total_output_area_m2_geod = 0.0

    for root_idx, idxs in groups.items():
        originals = [polys_utm[i] for i in idxs]

        SHELL = unary_union([p.buffer(tol_m) for p in originals]).buffer(-tol_m)

        # 1) Parte base: dissolve overlaps de verdade (unary_union já faz isso)
        parts = []
        for g in originals:
            parts.extend(polygon_parts(g))

        BASE = unary_union(parts)

        # 2) Corredores só para "pontes" quando há gap (distância > 0), conforme mst_edges ajustado
        corridors = []
        if len(parts) > 1:
            for a, b in mst_edges(parts, tol_m):
                Apt, Bpt = nearest_points(parts[a], parts[b])
                # evita corredor degenerado (mesmo ponto)
                if Apt.equals(Bpt):
                    continue
                line = LineString([Apt.coords[0], Bpt.coords[0]])
                buf = line.buffer(corridor_width_m / 2.0, cap_style=2, join_style=2)
                if buf and (not buf.is_empty):
                    corridors.append(buf)

        BASE = unary_union(parts + corridors)

        corridor_mask = unary_union(corridors) if corridors else None
        if corridor_mask and (not corridor_mask.is_empty):
            corridor_mask = corridor_mask.buffer(max(0.01, corridor_width_m * 0.6))

        # --- GARANTIA: FINAL_utm SEMPRE definido ---
        if corridor_mask and (not corridor_mask.is_empty):
            FINAL_utm = BASE.union(SHELL.intersection(corridor_mask))
        else:
            FINAL_utm = BASE

        # dissolve determinístico (agora é seguro)
        FINAL_utm = unary_union(FINAL_utm)

        # corrige inválidos
        if (FINAL_utm is not None) and (not FINAL_utm.is_empty) and (not FINAL_utm.is_valid):
            FINAL_utm = FINAL_utm.buffer(0)

        FINAL_ll = shp_transform(to_ll, FINAL_utm)




        total_output_area_m2_geod += geodesic_area_m2(FINAL_ll)

        finals_utm.append(FINAL_utm)
        finals_ll.append(FINAL_ll)
        finals_names.append(", ".join([names[i] for i in idxs]))

    def _pts_equal(a, b, eps=1e-12):
        return isclose(a[0], b[0], abs_tol=eps) and isclose(a[1], b[1], abs_tol=eps)

    def _clean_ring_for_kml(iterable_coords, eps=1e-12):
        coords = [(float(x), float(y)) for (x, y) in iterable_coords]

        cleaned = []
        last = None
        for pt in coords:
            if last is None or not _pts_equal(pt, last, eps):
                cleaned.append(pt)
                last = pt

        if not cleaned:
            return []

        if not _pts_equal(cleaned[0], cleaned[-1], eps):
            cleaned.append(cleaned[0])

        uniques = []
        for pt in cleaned[:-1]:
            if not uniques or not _pts_equal(pt, uniques[-1], eps):
                uniques.append(pt)

        if len(uniques) < 3:
            return []

        closed = uniques[:]
        if not _pts_equal(closed[0], closed[-1], eps):
            closed.append(closed[0])

        return closed

    def _coords_to_kml_str(coords, z_m=30.0):
        return " ".join(f"{x:.8f},{y:.8f},{z_m:.2f}" for (x, y) in coords)



    # métricas “output” em UTM (m²) e contagem de polígonos
    output_area_m2_utm = 0.0
    merged_polygons = 0
    for g in finals_utm:
        for p in polygon_parts(g):
            output_area_m2_utm += p.area
            merged_polygons += 1
    output_area_ha_utm = output_area_m2_utm / 10000.0

    # --------- KML ---------
    doc = Document()
    kml = doc.createElement("kml")
    kml.setAttribute("xmlns", "http://www.opengis.net/kml/2.2")
    doc.appendChild(kml)

    document = doc.createElement("Document")
    kml.appendChild(document)

    style = doc.createElement("Style")
    style.setAttribute("id", "styleMerged")

    # LineStyle (borda clara)
    ls = doc.createElement("LineStyle")
    lc = doc.createElement("color")
    lc.appendChild(doc.createTextNode("ffffffff"))  # branco sólido (KML ABGR)
    lw = doc.createElement("width")
    lw.appendChild(doc.createTextNode("2.5"))
    ls.appendChild(lc)
    ls.appendChild(lw)

    # PolyStyle (preenchimento forte)
    ps = doc.createElement("PolyStyle")
    pc = doc.createElement("color")
    pc.appendChild(doc.createTextNode(style_color))


    fill = doc.createElement("fill")
    fill.appendChild(doc.createTextNode("1"))

    outline = doc.createElement("outline")
    outline.appendChild(doc.createTextNode("1"))

    ps.appendChild(pc)
    ps.appendChild(fill)
    ps.appendChild(outline)

    style.appendChild(ls)
    style.appendChild(ps)
    document.appendChild(style)
    counter = 1
    for geom in finals_ll:
        for poly in polygon_parts(geom):  # <-- robusto (Polygon/Multi/Collection)
            poly = orient(poly, sign=1.0)  # outer CCW, holes CW
            outer_clean = _clean_ring_for_kml(list(poly.exterior.coords))
            # outer_clean = _clean_ring_for_kml(list(poly.exterior.coords))
            if not outer_clean:
                continue

            pm = doc.createElement("Placemark")
            nm = doc.createElement("name")
            nm.appendChild(doc.createTextNode(f"Area_{counter}"))
            su = doc.createElement("styleUrl")
            su.appendChild(doc.createTextNode("#styleMerged"))
            pm.appendChild(nm)
            pm.appendChild(su)

            pg = doc.createElement("Polygon")

            alt = doc.createElement("altitudeMode")
            alt.appendChild(doc.createTextNode("relativeToGround"))
            pg.appendChild(alt)

            extr = doc.createElement("extrude")
            extr.appendChild(doc.createTextNode("1"))
            pg.appendChild(extr)

            obi = doc.createElement("outerBoundaryIs")
            lr = doc.createElement("LinearRing")
            coords_el = doc.createElement("coordinates")
            coords_el.appendChild(
                doc.createTextNode(_coords_to_kml_str(outer_clean, z_m=30.0))
            )
            lr.appendChild(coords_el)
            obi.appendChild(lr)
            pg.appendChild(obi)

            for interior in poly.interiors:
                inner_clean = _clean_ring_for_kml(list(interior.coords))
                if not inner_clean:
                    continue
                ibi = doc.createElement("innerBoundaryIs")
                lr_i = doc.createElement("LinearRing")
                coords_i = doc.createElement("coordinates")
                coords_i.appendChild(doc.createTextNode(_coords_to_kml_str(inner_clean, z_m=30.0)))
                lr_i.appendChild(coords_i)
                ibi.appendChild(lr_i)
                pg.appendChild(ibi)

            pm.appendChild(pg)
            document.appendChild(pm)
            counter += 1

    kml_str = doc.toprettyxml(indent="  ")

    if return_metrics:
        metrics = {
            "input_area_m2": float(input_area_m2),
            "input_area_ha": float(input_area_ha),
            "output_area_m2": float(output_area_m2_utm),
            "output_area_ha": float(output_area_ha_utm),
            "merged_polygons": int(merged_polygons),
            "output_polygons": int(counter - 1),
            # se você quiser expor também a área geodésica (lon/lat):
            "output_area_m2_geodesic": float(total_output_area_m2_geod),
        }
        return kml_str, metrics

    return kml_str

from typing import List, Dict, Tuple
from math import isclose
from xml.dom.minidom import Document

from shapely.geometry import LineString, MultiLineString
from shapely.ops import nearest_points, transform as shp_transform, unary_union


def merge_no_flood_not_union(
    parcelas: List[Dict],
    tol_m: float = 20.0,
    corridor_width_m: float = 0.10,       # 10 cm (bem fino)
    style_color: str = "4d00ff00",  # ~30% verde (KML ABGR)
    return_metrics: bool = False,
    force_connect: bool = True,
    min_corridor_width_m: float = 0.10,   # piso 10 cm
    touch_bridge_len_m: float = 0.40,     # 40 cm quando dist==0
    max_rounds: int = 4,
    export_debug_lines: bool = True,      # ✅ deixa visível as “formas originais”
) -> str:
    """
    - Cria corredores mínimos para conectar (MST).
    - Faz unary_union(polys + corredores) => 1 único Polygon.
    - Opcional: exporta LineStrings com as bordas originais + linhas dos corredores
      (só visual; não altera a área final).
    """

    polys_ll, names = to_polygons_ll(parcelas)
    if not polys_ll:
        raise ValueError("Nenhuma parcela válida recebida.")

    epsg = choose_utm_epsg(polys_ll)
    groups, polys_utm, to_ll = build_groups_by_proximity(polys_ll, tol_m, epsg)

    input_area_m2 = sum(p.area for p in polys_utm)
    input_area_ha = input_area_m2 / 10000.0
    total_output_area_m2_geod = 0.0

    # ----------------- helpers -----------------

    def _fix(g):
        if g and (not g.is_empty) and (not g.is_valid):
            return g.buffer(0)
        return g

    def _pts_equal(a, b, eps=1e-12):
        return isclose(a[0], b[0], abs_tol=eps) and isclose(a[1], b[1], abs_tol=eps)

    def _clean_ring_for_kml(iterable_coords, eps=1e-12):
        coords = [(float(x), float(y)) for (x, y) in iterable_coords]

        cleaned = []
        last = None
        for pt in coords:
            if last is None or not _pts_equal(pt, last, eps):
                cleaned.append(pt)
                last = pt

        if not cleaned:
            return []

        if not _pts_equal(cleaned[0], cleaned[-1], eps):
            cleaned.append(cleaned[0])

        uniques = []
        for pt in cleaned[:-1]:
            if not uniques or not _pts_equal(pt, uniques[-1], eps):
                uniques.append(pt)

        if len(uniques) < 3:
            return []

        closed = uniques[:]
        if not _pts_equal(closed[0], closed[-1], eps):
            closed.append(closed[0])

        return closed

    def _coords_to_kml_str(coords, z_m=30.0):
        return " ".join(f"{x:.8f},{y:.8f},{z_m:.2f}" for (x, y) in coords)


    def _line_coords_to_kml_str(coords):
        return " ".join(f"{float(x):.8f},{float(y):.8f}" for (x, y) in coords)

    # ---------- MST (Kruskal) por distância borda-borda ----------
    def _mst_edges_by_geom_distance(geoms) -> List[Tuple[float, int, int]]:
        n = len(geoms)
        if n < 2:
            return []

        parent = list(range(n))
        rank = [0] * n

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra == rb:
                return False
            if rank[ra] < rank[rb]:
                parent[ra] = rb
            elif rank[ra] > rank[rb]:
                parent[rb] = ra
            else:
                parent[rb] = ra
                rank[ra] += 1
            return True

        edges = []
        for i in range(n):
            for j in range(i + 1, n):
                d = geoms[i].distance(geoms[j])  # UTM metros
                edges.append((d, i, j))

        edges.sort(key=lambda x: x[0])

        out = []
        for d, i, j in edges:
            if union(i, j):
                out.append((d, i, j))
                if len(out) == n - 1:
                    break
        return out

    def _unit_direction(a_geom, b_geom):
        pa = a_geom.representative_point()
        pb = b_geom.representative_point()
        dx = pb.x - pa.x
        dy = pb.y - pa.y
        norm = (dx * dx + dy * dy) ** 0.5
        if norm < 1e-9:
            return (1.0, 0.0)
        return (dx / norm, dy / norm)

    def _touch_bridge(a_geom, b_geom, contact_point, width_m: float, length_m: float):
        # micro-ponte curtinha atravessando o contato
        ux, uy = _unit_direction(a_geom, b_geom)
        L = max(float(length_m), width_m * 2.0, 0.2)

        x, y = float(contact_point.x), float(contact_point.y)
        p1 = (x - ux * (L / 2.0), y - uy * (L / 2.0))
        p2 = (x + ux * (L / 2.0), y + uy * (L / 2.0))

        line = LineString([p1, p2])
        buf = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
        return _fix(buf) if buf and not buf.is_empty else None, line

    def _gap_bridge(a_geom, b_geom, width_m: float):
        Apt, Bpt = nearest_points(a_geom, b_geom)
        line = LineString([Apt.coords[0], Bpt.coords[0]])
        buf = line.buffer(width_m / 2.0, cap_style=2, join_style=2)
        return _fix(buf) if buf and not buf.is_empty else None, line

    def _make_corridor(a_geom, b_geom, width_m: float):
        Apt, Bpt = nearest_points(a_geom, b_geom)
        if Apt.equals(Bpt):
            return _touch_bridge(a_geom, b_geom, Apt, width_m, touch_bridge_len_m)
        return _gap_bridge(a_geom, b_geom, width_m)

    def _connect_and_union(parts, width_m: float):
        """
        Conecta via MST com corredores mínimos e dissolve.
        Se ainda ficar MultiPolygon, conecta componentes e repete.
        """
        current = [_fix(p) for p in parts if p and not p.is_empty]
        if not current:
            return None, [], []

        corridors_used = []
        link_lines_used = []

        for _ in range(max_rounds):
            if len(current) <= 1:
                merged = _fix(unary_union(current))
                polys = polygon_parts(merged)
                return (polys[0] if len(polys) == 1 else merged), corridors_used, link_lines_used

            mst = _mst_edges_by_geom_distance(current)

            corridors = []
            for d, i, j in mst:
                cor, ln = _make_corridor(current[i], current[j], width_m)
                if cor is not None and (not cor.is_empty):
                    corridors.append(cor)
                    corridors_used.append(cor)
                if ln is not None and (not ln.is_empty):
                    link_lines_used.append(ln)

            merged = unary_union([*current, *corridors]) if corridors else unary_union(current)
            merged = _fix(merged)

            polys = polygon_parts(merged)
            if len(polys) == 1:
                return polys[0], corridors_used, link_lines_used

            current = polys

        merged = _fix(unary_union(current))
        polys = polygon_parts(merged)
        if polys:
            return max(polys, key=lambda g: g.area), corridors_used, link_lines_used
        return merged, corridors_used, link_lines_used

    # ----------------- coletar polígonos originais (UTM) -----------------
    all_parts_utm = []
    for _, idxs in groups.items():
        originals = [polys_utm[i] for i in idxs]
        for g in originals:
            for p in polygon_parts(g):
                p = _fix(p)
                if p and not p.is_empty:
                    all_parts_utm.append(p)

    if not all_parts_utm:
        raise ValueError("Nenhuma geometria poligonal válida para processar.")

    # largura efetiva (nunca 0)
    w = max(0.02, float(min_corridor_width_m or 0), float(corridor_width_m or 0))

    if force_connect:
        final_utm, corridors_used, link_lines_used = _connect_and_union(all_parts_utm, w)
    else:
        final_utm = _fix(unary_union(all_parts_utm))
        corridors_used, link_lines_used = [], []

    if final_utm is None or final_utm.is_empty:
        raise ValueError("Falha ao gerar geometria final.")

    final_ll = shp_transform(to_ll, final_utm)
    total_output_area_m2_geod += geodesic_area_m2(final_ll)

    # ----------------- métricas -----------------
    output_area_m2_utm = 0.0
    for p in polygon_parts(final_utm):
        output_area_m2_utm += p.area
    output_area_ha_utm = output_area_m2_utm / 10000.0

    # ----------------- KML -----------------
    doc = Document()
    kml = doc.createElement("kml")
    kml.setAttribute("xmlns", "http://www.opengis.net/kml/2.2")
    doc.appendChild(kml)

    document = doc.createElement("Document")
    kml.appendChild(document)

    # style do polígono final
    style = doc.createElement("Style")
    style.setAttribute("id", "styleMerged")

    # LineStyle (borda clara)
    ls = doc.createElement("LineStyle")
    lc = doc.createElement("color")
    lc.appendChild(doc.createTextNode("ffffffff"))  # branco sólido
    lw_el = doc.createElement("width")
    lw_el.appendChild(doc.createTextNode("2.5"))
    ls.appendChild(lc)
    ls.appendChild(lw_el)

    # PolyStyle (preenchimento)
    ps = doc.createElement("PolyStyle")
    pc = doc.createElement("color")
    pc.appendChild(doc.createTextNode(style_color))  # usa o param
    ps.appendChild(pc)

    fill = doc.createElement("fill")
    fill.appendChild(doc.createTextNode("1"))
    ps.appendChild(fill)

    outline = doc.createElement("outline")
    outline.appendChild(doc.createTextNode("1"))
    ps.appendChild(outline)

    style.appendChild(ls)
    style.appendChild(ps)
    document.appendChild(style)


    # style das linhas (debug visual)
    if export_debug_lines:
        style_lines = doc.createElement("Style")
        style_lines.setAttribute("id", "styleLines")

        lsL = doc.createElement("LineStyle")
        lcL = doc.createElement("color")
        lcL.appendChild(doc.createTextNode("ff00aaff"))  # azul claro
        lwL = doc.createElement("width")
        lwL.appendChild(doc.createTextNode("2"))
        lsL.appendChild(lcL)
        lsL.appendChild(lwL)

        style_lines.appendChild(lsL)
        document.appendChild(style_lines)

    # ---- Placemark 1: 1 Polygon final ----
    pm = doc.createElement("Placemark")
    nm = doc.createElement("name")
    nm.appendChild(doc.createTextNode("Merged_1"))
    su = doc.createElement("styleUrl")
    su.appendChild(doc.createTextNode("#styleMerged"))
    pm.appendChild(nm)
    pm.appendChild(su)

    polys_ll_out = polygon_parts(final_ll)
    if not polys_ll_out:
        raise ValueError("Não foi possível extrair polígono final para o KML.")
    poly = max(polys_ll_out, key=lambda g: g.area)

    outer_clean = _clean_ring_for_kml(list(poly.exterior.coords))
    if not outer_clean:
        raise ValueError("Anel externo inválido após limpeza.")

    pg = doc.createElement("Polygon")

    # ✅ ESSENCIAL para Earth Web
    alt = doc.createElement("altitudeMode")
    alt.appendChild(doc.createTextNode("relativeToGround"))
    pg.appendChild(alt)

    extr = doc.createElement("extrude")
    extr.appendChild(doc.createTextNode("1"))
    pg.appendChild(extr)

    obi = doc.createElement("outerBoundaryIs")
    obi = doc.createElement("outerBoundaryIs")
    lr = doc.createElement("LinearRing")
    coords_el = doc.createElement("coordinates")
    coords_el.appendChild(
        doc.createTextNode(_coords_to_kml_str(outer_clean, z_m=30.0))
    )

    lr.appendChild(coords_el)
    obi.appendChild(lr)
    pg.appendChild(obi)

    for interior in poly.interiors:
        inner_clean = _clean_ring_for_kml(list(interior.coords))
        if not inner_clean:
            continue
        ibi = doc.createElement("innerBoundaryIs")
        lr_i = doc.createElement("LinearRing")
        coords_i = doc.createElement("coordinates")
        coords_i.appendChild(
            doc.createTextNode(_coords_to_kml_str(inner_clean, z_m=30.0))
        )

        lr_i.appendChild(coords_i)
        ibi.appendChild(lr_i)
        pg.appendChild(ibi)

    pm.appendChild(pg)
    document.appendChild(pm)

    # ---- Placemark 2: linhas das bordas originais + conexões (visual) ----
    if export_debug_lines:
        # bordas originais
        border_lines = []
        for p in all_parts_utm:
            ll = shp_transform(to_ll, p)
            for poly_i in polygon_parts(ll):
                border_lines.append(LineString(list(poly_i.exterior.coords)))

        # linhas do MST (as conexões)
        conn_lines = [shp_transform(to_ll, ln) for ln in link_lines_used if ln and (not ln.is_empty)]

        # junta tudo num MultiLineString (se tiver)
        all_lines = [ln for ln in (border_lines + conn_lines) if ln and (not ln.is_empty)]

        if all_lines:
            pmL = doc.createElement("Placemark")
            nmL = doc.createElement("name")
            nmL.appendChild(doc.createTextNode("Original_Borders_And_Links"))
            suL = doc.createElement("styleUrl")
            suL.appendChild(doc.createTextNode("#styleLines"))
            pmL.appendChild(nmL)
            pmL.appendChild(suL)

            mgL = doc.createElement("MultiGeometry")

            for ln in all_lines:
                coords = list(ln.coords)
                if len(coords) < 2:
                    continue

                ls_el = doc.createElement("LineString")
                tess = doc.createElement("tessellate")
                tess.appendChild(doc.createTextNode("1"))
                ls_el.appendChild(tess)

                coords_el = doc.createElement("coordinates")
                coords_el.appendChild(doc.createTextNode(_line_coords_to_kml_str(coords)))
                ls_el.appendChild(coords_el)

                mgL.appendChild(ls_el)

            pmL.appendChild(mgL)
            document.appendChild(pmL)

    kml_str = doc.toprettyxml(indent="  ")
    
    def _line_to_coords_ll(line_ll):
        return [[float(x), float(y)] for (x, y) in list(line_ll.coords)]

    # links (MST)
    debug_links = []
    for ln in link_lines_used:
        ln_ll = shp_transform(to_ll, ln)
        if ln_ll and not ln_ll.is_empty:
            debug_links.append(_line_to_coords_ll(ln_ll))

    # bordas originais
    debug_borders = []
    for p in all_parts_utm:
        p_ll = shp_transform(to_ll, p)
        for poly in polygon_parts(p_ll):
            ring = list(poly.exterior.coords)
            if len(ring) >= 2:
                debug_borders.append([[float(x), float(y)] for (x, y) in ring])

    debug_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
            "type": "Feature",
            "properties": {"kind": "links"},
            "geometry": {"type": "MultiLineString", "coordinates": debug_links},
            },
            {
            "type": "Feature",
            "properties": {"kind": "borders"},
            "geometry": {"type": "MultiLineString", "coordinates": debug_borders},
            },
        ],
        }
    if return_metrics:
        metrics = {
            "input_area_m2": float(input_area_m2),
            "input_area_ha": float(input_area_ha),
            "output_area_m2": float(output_area_m2_utm),
            "output_area_ha": float(output_area_ha_utm),
            "output_polygons": 1,
            "corridor_width_used_m": float(w),
            "touch_bridge_len_m": float(touch_bridge_len_m),
            "corridors_used": int(len(corridors_used)),
            "parts_in": int(len(all_parts_utm)),
            "output_area_m2_geodesic": float(total_output_area_m2_geod),
        }
        return kml_str, metrics, debug_geojson

    return kml_str
