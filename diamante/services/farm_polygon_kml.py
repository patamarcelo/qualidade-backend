"""Export selected farm geometries without merging or simplifying their points."""

import math
from xml.etree import ElementTree as ET


def export_farm_polygons_kml(polygons):
    root = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(root, "Document")
    ET.SubElement(document, "name").text = "Polígonos selecionados"
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
        if polygon.is_closed:
            geometry = ET.SubElement(placemark, "Polygon")
            boundary = ET.SubElement(geometry, "outerBoundaryIs")
            geometry = ET.SubElement(boundary, "LinearRing")
        else:
            geometry = ET.SubElement(placemark, "LineString")
        ET.SubElement(geometry, "coordinates").text = " ".join(
            f"{lng},{lat},0" for lng, lat in coordinates
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
