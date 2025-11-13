from django.urls import path
from .views import KMLUnionView

urlpatterns = [
    path("kml-union/", KMLUnionView.as_view(), name="kml-union"),
]