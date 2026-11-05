from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import RequestFactory
from xml.etree import ElementTree as ET

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from diamante.admin import FarmPolygonAdmin
from diamante.models import FarmPolygon
from diamante.services.farm_polygon_kml import export_farm_polygons_kml


class FarmPolygonKMLTests(SimpleTestCase):
    def setUp(self):
        self.form_patch = patch("diamante.forms_kml_export.FarmPolygonExportForm")
        form = self.form_patch.start().return_value
        form.is_valid.return_value = True
        form.cleaned_data = {"color": "#35b637", "opacity": 50}
        self.addCleanup(self.form_patch.stop)
        self.request = RequestFactory().post("/", {"export_kml_confirm": "1"})

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
            self.request, queryset
        )
        self.assertEqual(response["Content-Type"], "application/vnd.google-earth.kml+xml")
        self.assertIn("poligonos_selecionados.kml", response["Content-Disposition"])
        root = ET.fromstring(response.content)
        places = root.findall("k:Document/k:Placemark", self.ns)
        self.assertEqual(len(places), 4)
        self.assertEqual(places[1].find("k:name", self.ns).text, polygons[0].name)
        self.assertIsNotNone(places[1].find("k:Point", self.ns))
        self.assertEqual(places[0].find("k:name", self.ns).text, polygons[0].name)
        ring = places[0].find("k:Polygon/k:outerBoundaryIs/k:LinearRing/k:coordinates", self.ns)
        self.assertEqual(ring.text.split(), ["0.0,0.0,0", "1.0,0.0,0", "1.0,1.0,0", "0.0,0.0,0"])
        self.assertEqual(places[2].find("k:LineString/k:coordinates", self.ns).text,
                         "-48.0,-15.0,0 -49.0,-16.0,0")

    def test_invalid_geometry_cancels_entire_download(self):
        model_admin = FarmPolygonAdmin(FarmPolygon, AdminSite())
        model_admin.message_user = Mock()
        queryset = Mock()
        queryset.iterator.return_value = iter([self.polygon(), self.polygon(points=[])])
        self.assertIsNone(model_admin.export_selected_kml(self.request, queryset))
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

    def test_fill_opacity_and_kml_channel_order(self):
        for opacity, expected in [(0, "00332211"), (50, "80332211"), (100, "ff332211")]:
            root = ET.fromstring(export_farm_polygons_kml([self.polygon()], "#112233", opacity))
            self.assertEqual(root.find(".//k:PolyStyle/k:color", self.ns).text, expected)

    def test_concave_polygon_label_stays_inside(self):
        from shapely.geometry import Polygon, Point
        coordinates = [(0, 0), (4, 0), (4, 4), (3, 4), (3, 1), (1, 1), (1, 4), (0, 4)]
        polygon = self.polygon(points=[{"lng": x, "lat": y} for x, y in coordinates])
        root = ET.fromstring(export_farm_polygons_kml([polygon]))
        marker = root.find(".//k:Point/k:coordinates", self.ns).text
        x, y, _ = map(float, marker.split(","))
        self.assertTrue(Polygon(coordinates).covers(Point(x, y)))

    def test_palette_and_opacity_validation(self):
        # Exercise the real form with a controlled culture palette.
        self.form_patch.stop()
        from diamante.forms_kml_export import FarmPolygonExportForm
        with patch("diamante.forms_kml_export.Cultura.objects") as cultures:
            cultures.exclude.return_value.exclude.return_value = []
            form = FarmPolygonExportForm({"color": "#000000", "opacity": 0})
            self.assertTrue(form.is_valid())
            self.assertFalse(FarmPolygonExportForm({"color": "#000000", "opacity": 101}).is_valid())

    def test_options_page_preserves_selection_across_pages(self):
        model_admin = FarmPolygonAdmin(FarmPolygon, AdminSite())
        request = RequestFactory().post("/", {"_selected_action": ["12", "34"], "select_across": "1"})
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        queryset = Mock()
        queryset.count.return_value = 40
        self.form_patch.stop()
        with patch("diamante.forms_kml_export.Cultura.objects") as cultures:
            cultures.exclude.return_value.exclude.return_value = []
            with patch.object(model_admin.admin_site, "each_context", return_value={"available_apps": [], "is_popup": False}):
                response = model_admin.export_selected_kml(request, queryset)
        self.assertEqual(response.context_data["selected_ids"], ["12", "34"])
        self.assertEqual(response.context_data["select_across"], "1")
        self.assertEqual(response.context_data["selection_count"], 40)
        response.render()
        self.assertContains(response, 'name="select_across" value="1"')
