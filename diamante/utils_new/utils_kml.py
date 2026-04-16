import math
import xml.etree.ElementTree as ET


def _parse_coordinates_text(raw_text):
    """
    Recebe texto no formato:
    -51.123, -29.123,0 -51.124,-29.124,0 ...
    e retorna [{'lat': ..., 'lng': ...}, ...]
    """
    points = []
    if not raw_text:
        return points

    chunks = raw_text.strip().split()
    for chunk in chunks:
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) < 2:
            continue

        try:
            lng = float(parts[0])
            lat = float(parts[1])
        except (TypeError, ValueError):
            continue

        points.append({"lat": lat, "lng": lng})

    return points


def _close_if_needed(points):
    if not points:
        return points

    first = points[0]
    last = points[-1]
    if first["lat"] != last["lat"] or first["lng"] != last["lng"]:
        return points + [first]
    return points


def _polygon_area_m2(points):
    """
    Aproximação planar simples.
    Boa para preview/admin. Se quiser precisão geodésica depois, troca por pyproj/shapely.
    """
    if len(points) < 3:
        return 0.0

    pts = _close_if_needed(points)
    lat0 = math.radians(sum(p["lat"] for p in pts) / len(pts))
    m_per_deg_lat = 111320.0
    m_per_deg_lng = 111320.0 * math.cos(lat0)

    xy = [(p["lng"] * m_per_deg_lng, p["lat"] * m_per_deg_lat) for p in pts]

    area = 0.0
    for i in range(len(xy) - 1):
        x1, y1 = xy[i]
        x2, y2 = xy[i + 1]
        area += (x1 * y2) - (x2 * y1)

    return abs(area) / 2.0


def _perimeter_m(points, closed=True):
    if len(points) < 2:
        return 0.0

    pts = _close_if_needed(points) if closed else points
    total = 0.0

    for i in range(len(pts) - 1):
        lat1, lng1 = pts[i]["lat"], pts[i]["lng"]
        lat2, lng2 = pts[i + 1]["lat"], pts[i + 1]["lng"]

        # haversine simples
        r = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lng2 - lng1)

        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        total += r * c

    return total


def parse_kml_content(kml_content):
    """
    Retorna:
    {
        "points": [...],
        "is_closed": True/False,
        "area_m2": float,
        "perimeter_m": float,
    }
    """
    if not kml_content:
        return {
            "points": [],
            "is_closed": True,
            "area_m2": 0.0,
            "perimeter_m": 0.0,
        }

    root = ET.fromstring(kml_content)
    ns = {
        "kml": "http://www.opengis.net/kml/2.2"
    }

    polygon_coords = root.find(".//kml:Polygon//kml:coordinates", ns)
    line_coords = root.find(".//kml:LineString//kml:coordinates", ns)

    is_closed = True
    coords_node = polygon_coords

    if coords_node is None:
        coords_node = line_coords
        is_closed = False

    if coords_node is None or not coords_node.text:
        return {
            "points": [],
            "is_closed": is_closed,
            "area_m2": 0.0,
            "perimeter_m": 0.0,
        }

    points = _parse_coordinates_text(coords_node.text)

    if is_closed and len(points) >= 3:
        area_m2 = _polygon_area_m2(points)
    else:
        area_m2 = 0.0

    perimeter_m = _perimeter_m(points, closed=is_closed)

    return {
        "points": points,
        "is_closed": is_closed,
        "area_m2": area_m2,
        "perimeter_m": perimeter_m,
    }