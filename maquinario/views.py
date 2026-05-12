from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Machine,
    HourmeterReading,
    MaintenanceRecord,
    MachineAlertRule,
    MaintenancePlan
)
from .serializers import (
    MachineListSerializer,
    MachineDetailSerializer,
    HourmeterReadingSerializer,
    CreateHourmeterReadingSerializer,
    MaintenanceRecordSerializer,
    MachineAlertRuleSerializer,
    MaintenancePlanSerializer
)


from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q


from decimal import Decimal, InvalidOperation
from django.utils import timezone

from django.http import HttpResponse
from openpyxl import Workbook


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

    @action(detail=True, methods=["post"])
    def update_hourmeter(self, request, pk=None):
        machine = self.get_object()

        value = request.data.get("value")
        measured_at = request.data.get("measured_at")
        source = request.data.get("source") or HourmeterReading.Source.APP
        notes = request.data.get("notes") or ""
        user_data = request.data.get("user") or {}

        if value in [None, ""]:
            return Response(
                {"error": "Informe o horímetro."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            value_decimal = Decimal(str(value).replace(",", "."))
        except (InvalidOperation, ValueError):
            return Response(
                {"error": "Horímetro inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if value_decimal < 0:
            return Response(
                {"error": "Horímetro não pode ser negativo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if machine.current_hourmeter and value_decimal < machine.current_hourmeter:
            return Response(
                {
                    "error": "O novo horímetro não pode ser menor que o horímetro atual.",
                    "current_hourmeter": str(machine.current_hourmeter),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reading = HourmeterReading.objects.create(
            machine=machine,
            value=value_decimal,
            measured_at=measured_at or timezone.now(),
            source=source,
            notes=notes,
        )

        machine.refresh_from_db()

        serializer = MachineDetailSerializer(machine)

        return Response({
            "message": "Horímetro atualizado com sucesso.",
            "reading": HourmeterReadingSerializer(reading).data,
            "machine": serializer.data,
            "user": {
                "email": user_data.get("email"),
                "uid": user_data.get("uid"),
                "displayName": user_data.get("displayName"),
            },
        })
        
        

    @action(detail=True, methods=["post"])
    def register_maintenance(self, request, pk=None):
        machine = self.get_object()

        maintenance_plan_id = request.data.get("maintenance_plan")
        hourmeter = request.data.get("hourmeter")
        performed_at = request.data.get("performed_at")
        description = request.data.get("description")
        user_data = request.data.get("user") or {}

        if hourmeter in [None, ""]:
            return Response(
                {"error": "Informe o horímetro da revisão."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            hourmeter_decimal = Decimal(str(hourmeter).replace(",", "."))
        except (InvalidOperation, ValueError):
            return Response(
                {"error": "Horímetro inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hourmeter_decimal < 0:
            return Response(
                {"error": "Horímetro não pode ser negativo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        maintenance_plan = None

        if maintenance_plan_id:
            maintenance_plan = (
                MaintenancePlan.objects
                .filter(
                    id=maintenance_plan_id,
                    farms=machine.fazenda,
                    is_active=True,
                )
                .first()
            )

            if not maintenance_plan:
                return Response(
                    {"error": "Plano de manutenção não encontrado para essa fazenda."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            selected_machine_types = maintenance_plan.machine_types or []

            if selected_machine_types and machine.machine_type not in selected_machine_types:
                return Response(
                    {"error": "Plano de manutenção não se aplica ao tipo dessa máquina."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        record = MaintenanceRecord.objects.create(
            machine=machine,
            maintenance_plan=maintenance_plan,
            maintenance_type=MaintenanceRecord.MaintenanceType.REVISION,
            performed_at=performed_at or timezone.now(),
            hourmeter=hourmeter_decimal,
            description=description,
        )

        machine.refresh_from_db()

        return Response({
            "message": "Revisão registrada com sucesso.",
            "maintenance": MaintenanceRecordSerializer(record).data,
            "machine": MachineDetailSerializer(machine).data,
            "user": {
                "email": user_data.get("email"),
                "uid": user_data.get("uid"),
                "displayName": user_data.get("displayName"),
            },
        })
        
            
    @action(detail=False, methods=["post"])
    def export_excel(self, request):
        fazenda_id = request.data.get("fazenda_id")
        search = request.data.get("search") or ""
        status_values = request.data.get("status") or []
        machine_types = request.data.get("machine_type") or []

        queryset = Machine.objects.select_related("fazenda").filter(is_active=True)

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

        machines = queryset.order_by("identifier").prefetch_related(
            "maintenance_records",
            "maintenance_records__maintenance_plan",
        )

        plans = (
            MaintenancePlan.objects
            .filter(is_active=True)
            .prefetch_related("farms")
            .order_by("interval_hours", "name")
        )

        if fazenda_id:
            plans = plans.filter(farms__id=fazenda_id).distinct()

        wb = Workbook()
        ws = wb.active
        ws.title = "Máquinas"

        base_headers = [
            "Identificador",
            "Descrição",
            "Chassi",
            "Tipo",
            "Status",
            "Horímetro atual",
            "Última leitura",
            "Plano mais próximo",
            "Próxima revisão geral",
            "Horas restantes geral",
            "Dias estimados geral",
        ]

        plan_headers = []

        for plan in plans:
            label = f"{plan.name} ({plan.interval_hours}h)"
            plan_headers.extend([
                f"Última - {label}",
                f"Data última - {label}",
                f"Próxima - {label}",
                f"Faltam h - {label}",
                f"Vencida - {label}",
            ])

        ws.append(base_headers + plan_headers)

        for machine in machines:
            next_due = machine.get_next_due_maintenance_item()

            if next_due:
                next_due_plan_name = next_due.get("plan_name") or ""
                next_due_hourmeter = next_due.get("next_revision_hourmeter")
                next_due_hours = next_due.get("hours_to_next_revision")
            else:
                next_due_plan_name = ""
                next_due_hourmeter = None
                next_due_hours = None

            days_to_next = ""

            if next_due_hours is not None and machine.average_hours_per_day and machine.average_hours_per_day > 0:
                days_to_next = int(
                    (next_due_hours / machine.average_hours_per_day)
                    .to_integral_value(rounding="ROUND_CEILING")
                )

            row = [
                machine.identifier,
                machine.description,
                machine.chassis or "",
                machine.get_machine_type_display(),
                machine.get_status_display(),
                float(machine.current_hourmeter or 0),
                machine.last_hourmeter_at.strftime("%d/%m/%Y %H:%M") if machine.last_hourmeter_at else "",
                next_due_plan_name,
                float(next_due_hourmeter) if next_due_hourmeter is not None else "",
                float(next_due_hours) if next_due_hours is not None else "",
                days_to_next,
            ]

            summary = machine.get_maintenance_summary()
            summary_by_plan_id = {
                item["plan_id"]: item
                for item in summary
            }

            for plan in plans:
                item = summary_by_plan_id.get(plan.id)

                if not item:
                    row.extend(["", "", "", "", ""])
                    continue

                last_revision_hourmeter = item.get("last_revision_hourmeter")
                last_revision_at = item.get("last_revision_at")
                next_revision_hourmeter = item.get("next_revision_hourmeter")
                hours_to_next_revision = item.get("hours_to_next_revision")
                is_due = item.get("is_due")

                row.extend([
                    float(last_revision_hourmeter) if last_revision_hourmeter is not None else "",
                    last_revision_at.strftime("%d/%m/%Y %H:%M") if last_revision_at else "",
                    float(next_revision_hourmeter) if next_revision_hourmeter is not None else "",
                    float(hours_to_next_revision) if hours_to_next_revision is not None else "",
                    "Sim" if is_due else "Não",
                ])

            ws.append(row)

        for column_cells in ws.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:
                value = str(cell.value or "")
                max_length = max(max_length, len(value))

            ws.column_dimensions[column_letter].width = min(max_length + 2, 42)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="relatorio_maquinas.xlsx"'

        wb.save(response)

        return response

    @action(detail=False, methods=["post"])
    def list_app(self, request):
        fazenda_id = request.data.get("fazenda_id")
        status_values = request.data.get("status") or []
        machine_types = request.data.get("machine_type") or []
        manager_id = request.data.get("manager_id")
        search = request.data.get("search") or ""
        user_data = request.data.get("user") or {}
        
        print("MAQUINARIO list_app user_data:", user_data)
        print("MAQUINARIO list_app customClaims:", user_data.get("customClaims"))
        print("MAQUINARIO list_app payload:", request.data)

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
    
    @action(detail=True, methods=["get"])
    def maintenance_summary(self, request, pk=None):
        machine = self.get_object()

        summary = machine.get_maintenance_summary()

        data = []

        for item in summary:
            data.append({
                "plan_id": item["plan_id"],
                "plan_name": item["plan_name"],
                "interval_hours": float(item["interval_hours"]),
                "last_record_id": item["last_record_id"],
                "last_revision_hourmeter": (
                    float(item["last_revision_hourmeter"])
                    if item["last_revision_hourmeter"] is not None
                    else None
                ),
                "last_revision_at": item["last_revision_at"],
                "next_revision_hourmeter": (
                    float(item["next_revision_hourmeter"])
                    if item["next_revision_hourmeter"] is not None
                    else None
                ),
                "hours_to_next_revision": (
                    float(item["hours_to_next_revision"])
                    if item["hours_to_next_revision"] is not None
                    else None
                ),
                "is_due": item["is_due"],
            })

        return Response({
            "machine": {
                "id": machine.id,
                "identifier": machine.identifier,
                "description": machine.description,
                "current_hourmeter": float(machine.current_hourmeter or 0),
            },
            "summary": data,
        })


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


class MaintenancePlanViewSet(viewsets.ModelViewSet):
    queryset = MaintenancePlan.objects.prefetch_related("farms").all()
    serializer_class = MaintenancePlanSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        fazenda_id = self.request.query_params.get("fazenda_id")
        machine_type = self.request.query_params.get("machine_type")
        active = self.request.query_params.get("active")

        if fazenda_id:
            queryset = queryset.filter(farms__id=fazenda_id)

        if active in ["true", "1", "yes"]:
            queryset = queryset.filter(is_active=True)

        queryset = queryset.distinct().order_by("interval_hours", "name")

        if machine_type:
            matching_ids = []

            for plan in queryset:
                selected_machine_types = plan.machine_types or []

                if not selected_machine_types or machine_type in selected_machine_types:
                    matching_ids.append(plan.id)

            queryset = MaintenancePlan.objects.filter(id__in=matching_ids).prefetch_related("farms")

        return queryset