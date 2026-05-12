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


from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

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


    @action(detail=False, methods=["post"])
    def list_app(self, request):
        fazenda_id = request.data.get("fazenda_id")
        status_values = request.data.get("status") or []
        machine_types = request.data.get("machine_type") or []
        manager_id = request.data.get("manager_id")
        search = request.data.get("search") or ""
        user_data = request.data.get("user") or {}

        queryset = (
            Machine.objects
            .select_related("fazenda")
            .filter(is_active=True)
        )

        if fazenda_id:
            queryset = queryset.filter(fazenda_id=fazenda_id)

        if status_values:
            queryset = queryset.filter(status__in=status_values)

        if machine_types:
            queryset = queryset.filter(machine_type__in=machine_types)

        if search:
            queryset = queryset.filter(
                Q(identifier__icontains=search)
                | Q(description__icontains=search)
                | Q(chassis__icontains=search)
                | Q(brand__icontains=search)
                | Q(model_name__icontains=search)
            )

        # Futuro:
        # aqui entra filtro por responsabilidade/manager.
        # Exemplo quando existir vínculo Machine <-> Manager:
        #
        # if manager_id:
        #     queryset = queryset.filter(responsible_managers__id=manager_id)
        #
        # ou usando o e-mail/uid enviado:
        #
        # user_email = user_data.get("email")
        # user_uid = user_data.get("uid")

        machines = queryset.order_by("identifier")

        serializer = MachineListSerializer(machines, many=True)

        return Response({
            "data": serializer.data,
            "totals": {
                "total": machines.count(),
                "operation": machines.filter(status=Machine.Status.OPERATION).count(),
                "revision": machines.filter(status=Machine.Status.REVISION).count(),
                "maintenance": machines.filter(status=Machine.Status.MAINTENANCE).count(),
            },
            "filters": {
                "fazenda_id": fazenda_id,
                "status": status_values,
                "machine_type": machine_types,
                "manager_id": manager_id,
                "search": search,
            },
            "user": {
                "email": user_data.get("email"),
                "uid": user_data.get("uid"),
            },
        })
        
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