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
    VisitasConsultasApi,
    RegistroVisitasApi,
    PlantioDetailResumoApi,
    StViewSet,
    ColheitaPlantioExtratoAreaViewSet,
    BackgroundTaskStatusViewSet,
    task_status_view,
    FarmPolygonViewSet,
)

router = routers.DefaultRouter()
router.register("", TalaoViewSet)
router.register("plantio", PlantioViewSet)
router.register("defensivo", DefensivoViewSet)
router.register("programas", ProgramasDetails)
router.register("colheita", ColheitaApiSave)
router.register("visitas", VisitasConsultasApi)
router.register("registrosvisita", RegistroVisitasApi)
router.register("resumocolheita", PlantioDetailResumoApi)
router.register("opensts", StViewSet)
router.register("extratocolheitaarea", ColheitaPlantioExtratoAreaViewSet)
router.register("backgroundtask", BackgroundTaskStatusViewSet)
router.register(r"polygons", FarmPolygonViewSet, basename="farm-polygon")


farm_polygon_list = FarmPolygonViewSet.as_view({
    "get": "list",
    "post": "create",
})

farm_polygon_detail = FarmPolygonViewSet.as_view({
    "get": "retrieve",
    "put": "update",
    "patch": "partial_update",
    "delete": "destroy",
})

urlpatterns = [
    path("polygons/", farm_polygon_list, name="farm-polygon-list"),
    path("polygons/<int:pk>/", farm_polygon_detail, name="farm-polygon-detail"),

    path(
        "backgroundtask_status/<uuid:task_id>/",
        task_status_view,
        name="backgroundtask-task-status",
    ),

    path("", include(router.urls)),
]

