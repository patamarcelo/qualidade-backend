from django.contrib import admin
from django.urls import path
from rest_framework import routers
from django.conf.urls import include

from .views_api import TalaoViewSet, PlantioViewSet

router = routers.DefaultRouter()
router.register("", TalaoViewSet)
router.register("plantio", PlantioViewSet)


urlpatterns = [
    path("", include(router.urls)),
]
