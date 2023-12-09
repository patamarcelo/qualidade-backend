from django.contrib import admin
from django.urls import path
from rest_framework import routers
from django.conf.urls import include

from .views_api import (
    TalaoViewSet,
    PlantioViewSet,
    DefensivoViewSet,
    ProgramasDetails,
    ColheitaApiSave,
)

router = routers.DefaultRouter()
router.register("", TalaoViewSet)
router.register("plantio", PlantioViewSet)
router.register("defensivo", DefensivoViewSet)
router.register("programas", ProgramasDetails)
router.register("colheita", ColheitaApiSave)


urlpatterns = [
    path("", include(router.urls)),
]
