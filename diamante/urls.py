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


urlpatterns = [
    path("", include(router.urls)),
    # 👇 ROTA MANUAL ADICIONADA
    path(
        "backgroundtask_status/<uuid:task_id>/",
        task_status_view,
        name="backgroundtask-task-status",
),
]
