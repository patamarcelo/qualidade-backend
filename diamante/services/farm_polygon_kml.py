"""Export selected farm geometries without merging or simplifying their points."""

import math
import re
from shapely.geometry import Polygon, LineString
from xml.etree import ElementTree as ET


def export_farm_polygons_kml(polygons, color="#35b637", opacity=50):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color) or not 0 <= opacity <= 100:
        raise ValueError("Cor ou opacidade inválida.")
    rgb = color[1:]
    bgr = rgb[4:6] + rgb[2:4] + rgb[0:2]
    fill = f"{round(opacity * 255 / 100):02x}" + bgr
    root = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(root, "Document")
    ET.SubElement(document, "name").text = "Polígonos selecionados"
    style = ET.SubElement(document, "Style", id="polygon-style")
    line = ET.SubElement(style, "LineStyle")
    ET.SubElement(line, "color").text = "ff" + bgr
    ET.SubElement(line, "width").text = "2"
    ET.SubElement(ET.SubElement(style, "PolyStyle"), "color").text = fill
    label_style = ET.SubElement(document, "Style", id="label-style")
    ET.SubElement(ET.SubElement(label_style, "IconStyle"), "scale").text = "0"
    label = ET.SubElement(label_style, "LabelStyle")
    ET.SubElement(label, "color").text = "ffffffff"
    ET.SubElement(label, "scale").text = "1.2"
    for polygon in polygons:
        coordinates = []
        for point in polygon.points or []:
            try:
                lng = next(point[key] for key in ("lng", "longitude", "lon")
                           if point.get(key) is not None)
                lat = next(point[key] for key in ("lat", "latitude")
                           if point.get(key) is not None)
                lng, lat = float(lng), float(lat)
                if not (math.isfinite(lng) and math.isfinite(lat)
                        and -180 <= lng <= 180 and -90 <= lat <= 90):
                    raise ValueError
            except (AttributeError, TypeError, ValueError, StopIteration, OverflowError):
                raise ValueError(f"{polygon.name}: coordenadas inválidas.") from None
            coordinates.append((lng, lat))

        minimum = 3 if polygon.is_closed else 2
        if len(set(coordinates)) < minimum:
            raise ValueError(f"{polygon.name}: pontos insuficientes para exportação.")
        if polygon.is_closed and coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])

        placemark = ET.SubElement(document, "Placemark")
        ET.SubElement(placemark, "name").text = polygon.name
        ET.SubElement(placemark, "description").text = f"Fazenda: {polygon.farm_name}"
        ET.SubElement(placemark, "styleUrl").text = "#polygon-style"
        if polygon.is_closed:
            geometry = ET.SubElement(placemark, "Polygon")
            boundary = ET.SubElement(geometry, "outerBoundaryIs")
            geometry = ET.SubElement(boundary, "LinearRing")
        else:
            geometry = ET.SubElement(placemark, "LineString")
        ET.SubElement(geometry, "coordinates").text = " ".join(
            f"{lng},{lat},0" for lng, lat in coordinates
        )
        shape = Polygon(coordinates) if polygon.is_closed else LineString(coordinates)
        center = shape.centroid
        if polygon.is_closed and not shape.covers(center):
            center = shape.representative_point()
        marker = ET.SubElement(document, "Placemark")
        ET.SubElement(marker, "name").text = polygon.name
        ET.SubElement(marker, "styleUrl").text = "#label-style"
        ET.SubElement(ET.SubElement(marker, "Point"), "coordinates").text = f"{center.x},{center.y},0"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
