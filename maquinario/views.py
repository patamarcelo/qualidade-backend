from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Machine,
    HourmeterReading,
    MaintenanceRecord,
    MachineAlertRule,
)
from .serializers import (
    MachineListSerializer,
    MachineDetailSerializer,
    HourmeterReadingSerializer,
    CreateHourmeterReadingSerializer,
    MaintenanceRecordSerializer,
    MachineAlertRuleSerializer,
)


class MachineViewSet(viewsets.ModelViewSet):
    queryset = (
        Machine.objects
        .select_related("fazenda")
        .all()
    )

    def get_serializer_class(self):
        if self.action == "list":
            return MachineListSerializer

        return MachineDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        fazenda_id = self.request.query_params.get("fazenda_id")
        status_value = self.request.query_params.get("status")
        machine_type = self.request.query_params.get("machine_type")
        active = self.request.query_params.get("active")

        if fazenda_id:
            queryset = queryset.filter(fazenda_id=fazenda_id)

        if status_value:
            queryset = queryset.filter(status=status_value)

        if machine_type:
            queryset = queryset.filter(machine_type=machine_type)

        if active in ["true", "1", "yes"]:
            queryset = queryset.filter(is_active=True)

        if active in ["false", "0", "no"]:
            queryset = queryset.filter(is_active=False)

        return queryset.order_by("identifier")

    @action(detail=True, methods=["get"])
    def readings(self, request, pk=None):
        machine = self.get_object()

        readings = (
            machine.hourmeter_readings
            .all()
            .order_by("-measured_at", "-id")[:50]
        )

        serializer = HourmeterReadingSerializer(readings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def add_reading(self, request, pk=None):
        machine = self.get_object()

        serializer = CreateHourmeterReadingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reading = serializer.save(machine=machine)

        output = HourmeterReadingSerializer(reading)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def maintenance_records(self, request, pk=None):
        machine = self.get_object()

        records = (
            machine.maintenance_records
            .all()
            .order_by("-performed_at", "-id")[:50]
        )

        serializer = MaintenanceRecordSerializer(records, many=True)
        return Response(serializer.data)


class HourmeterReadingViewSet(viewsets.ModelViewSet):
    queryset = (
        HourmeterReading.objects
        .select_related("machine", "machine__fazenda")
        .all()
    )
    serializer_class = HourmeterReadingSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        machine_id = self.request.query_params.get("machine_id")
        fazenda_id = self.request.query_params.get("fazenda_id")

        if machine_id:
            queryset = queryset.filter(machine_id=machine_id)

        if fazenda_id:
            queryset = queryset.filter(machine__fazenda_id=fazenda_id)

        return queryset.order_by("-measured_at", "-id")


class MaintenanceRecordViewSet(viewsets.ModelViewSet):
    queryset = (
        MaintenanceRecord.objects
        .select_related("machine", "machine__fazenda")
        .all()
    )
    serializer_class = MaintenanceRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        machine_id = self.request.query_params.get("machine_id")
        fazenda_id = self.request.query_params.get("fazenda_id")

        if machine_id:
            queryset = queryset.filter(machine_id=machine_id)

        if fazenda_id:
            queryset = queryset.filter(machine__fazenda_id=fazenda_id)

        return queryset.order_by("-performed_at", "-id")


class MachineAlertRuleViewSet(viewsets.ModelViewSet):
    queryset = (
        MachineAlertRule.objects
        .select_related("machine", "machine__fazenda")
        .prefetch_related("managers")
        .all()
    )
    serializer_class = MachineAlertRuleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        machine_id = self.request.query_params.get("machine_id")
        fazenda_id = self.request.query_params.get("fazenda_id")

        if machine_id:
            queryset = queryset.filter(machine_id=machine_id)

        if fazenda_id:
            queryset = queryset.filter(machine__fazenda_id=fazenda_id)

        return queryset.order_by("machine__identifier")