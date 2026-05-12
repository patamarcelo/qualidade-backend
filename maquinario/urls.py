from rest_framework.routers import DefaultRouter

from .views import (
    MachineViewSet,
    HourmeterReadingViewSet,
    MaintenanceRecordViewSet,
    MachineAlertRuleViewSet,
    MaintenancePlanViewSet
)

router = DefaultRouter()

router.register("machines", MachineViewSet, basename="machines")
router.register("hourmeter-readings", HourmeterReadingViewSet, basename="hourmeter-readings")
router.register("maintenance-records", MaintenanceRecordViewSet, basename="maintenance-records")
router.register("alert-rules", MachineAlertRuleViewSet, basename="alert-rules")
router.register("maintenance-plans", MaintenancePlanViewSet, basename="maintenance-plans")

urlpatterns = router.urls