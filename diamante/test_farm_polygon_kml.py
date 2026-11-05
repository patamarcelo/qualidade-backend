from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from diamante.admin import FarmPolygonAdmin
from diamante.models import FarmPolygon
from diamante.services.farm_polygon_kml import export_farm_polygons_kml


class FarmPolygonKMLTests(SimpleTestCase):
    ns = {"k": "http://www.opengis.net/kml/2.2"}

    def polygon(self, **overrides):
        data = dict(name="Talhão <A> & B", farm_name="Fazenda & Cia",
                    is_closed=True, points=[{"lng": 0, "lat": 0},
                                            {"lng": 1, "lat": 0},
                                            {"lng": 1, "lat": 1}])
        data.update(overrides)
        return SimpleNamespace(**data)

    def test_action_downloads_all_selected_geometries_in_one_document(self):
        polygons = [self.polygon(), self.polygon(name="Linha", is_closed=False,
                    points=[{"longitude": -48, "latitude": -15},
                            {"lon": -49, "lat": -16}])]
        queryset = Mock()
        queryset.iterator.return_value = iter(polygons)
        response = FarmPolygonAdmin(FarmPolygon, AdminSite()).export_selected_kml(
            None, queryset
        )
        self.assertEqual(response["Content-Type"], "application/vnd.google-earth.kml+xml")
        self.assertIn("poligonos_selecionados.kml", response["Content-Disposition"])
        root = ET.fromstring(response.content)
        places = root.findall("k:Document/k:Placemark", self.ns)
        self.assertEqual(len(places), 2)
        self.assertEqual(places[0].find("k:name", self.ns).text, polygons[0].name)
        ring = places[0].find("k:Polygon/k:outerBoundaryIs/k:LinearRing/k:coordinates", self.ns)
        self.assertEqual(ring.text.split(), ["0.0,0.0,0", "1.0,0.0,0", "1.0,1.0,0", "0.0,0.0,0"])
        self.assertEqual(places[1].find("k:LineString/k:coordinates", self.ns).text,
                         "-48.0,-15.0,0 -49.0,-16.0,0")

    def test_invalid_geometry_cancels_entire_download(self):
        model_admin = FarmPolygonAdmin(FarmPolygon, AdminSite())
        model_admin.message_user = Mock()
        queryset = Mock()
        queryset.iterator.return_value = iter([self.polygon(), self.polygon(points=[])])
        self.assertIsNone(model_admin.export_selected_kml(None, queryset))
        self.assertIn("Nenhum item foi exportado", model_admin.message_user.call_args.args[1])

    def test_rejects_invalid_coordinates_without_silently_dropping_points(self):
        for point in ({"lng": "NaN", "lat": 1}, {"lng": 181, "lat": 0},
                      {"lng": 0}, None):
            with self.subTest(point=point), self.assertRaises(ValueError):
                export_farm_polygons_kml([self.polygon(points=[point])])

    def test_does_not_duplicate_existing_ring_closure(self):
        polygon = self.polygon()
        polygon.points.append(polygon.points[0])
        root = ET.fromstring(export_farm_polygons_kml([polygon]))
        coordinates = root.find(".//k:coordinates", self.ns).text.split()
        self.assertEqual(len(coordinates), 4)
