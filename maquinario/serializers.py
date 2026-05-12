from rest_framework import serializers

from .models import (
    Machine,
    HourmeterReading,
    MaintenanceRecord,
    MachineAlertRule,
    MaintenancePlan,
)


class MachineListSerializer(serializers.ModelSerializer):
    last_revision_hourmeter = serializers.SerializerMethodField()
    next_revision_hourmeter = serializers.SerializerMethodField()
    hours_to_next_revision = serializers.SerializerMethodField()
    estimated_days_to_next_revision = serializers.SerializerMethodField()
    revision_progress_percent = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    machine_type_label = serializers.CharField(source="get_machine_type_display", read_only=True)
    maintenance_summary = serializers.SerializerMethodField()
    next_due_maintenance = serializers.SerializerMethodField()

    class Meta:
        model = Machine
        fields = [
            "id",
            "identifier",
            "chassis",
            "description",
            "machine_type",
            "machine_type_label",
            "brand",
            "model_name",
            "status",
            "status_label",
            "current_hourmeter",
            "last_hourmeter_at",
            "last_revision_hourmeter",
            "next_revision_hourmeter",
            "revision_interval_hours",
            "average_hours_per_day",
            "hours_to_next_revision",
            "estimated_days_to_next_revision",
            "revision_progress_percent",
            "maintenance_summary",
            "next_due_maintenance",
        ]

    def get_last_revision_hourmeter(self, obj):
        next_due = obj.get_next_due_maintenance_item()

        if next_due and next_due.get("last_revision_hourmeter") is not None:
            return float(next_due["last_revision_hourmeter"])

        value = obj.last_revision_hourmeter
        return None if value is None else float(value)


    def get_next_revision_hourmeter(self, obj):
        next_due = obj.get_next_due_maintenance_item()

        if next_due and next_due.get("next_revision_hourmeter") is not None:
            return float(next_due["next_revision_hourmeter"])

        value = obj.next_revision_hourmeter
        return None if value is None else float(value)
    
    def get_hours_to_next_revision(self, obj):
        next_due = obj.get_next_due_maintenance_item()

        if next_due and next_due.get("hours_to_next_revision") is not None:
            return float(next_due["hours_to_next_revision"])

        value = obj.hours_to_next_revision
        return None if value is None else float(value)

    def get_estimated_days_to_next_revision(self, obj):
        next_due = obj.get_next_due_maintenance_item()

        if next_due and next_due.get("hours_to_next_revision") is not None:
            hours_to_next = next_due["hours_to_next_revision"]

            if obj.average_hours_per_day and obj.average_hours_per_day > 0:
                return int(
                    (hours_to_next / obj.average_hours_per_day)
                    .to_integral_value(rounding="ROUND_CEILING")
                )

        return obj.estimated_days_to_next_revision

    def get_revision_progress_percent(self, obj):
        return obj.revision_progress_percent

    def get_maintenance_summary(self, obj):
        summary = obj.get_maintenance_summary()

        return [
            {
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
            }
            for item in summary
        ]

    def get_next_due_maintenance(self, obj):
        item = obj.get_next_due_maintenance_item()

        if not item:
            return None

        return {
            "plan_id": item["plan_id"],
            "plan_name": item["plan_name"],
            "interval_hours": float(item["interval_hours"]),
            "last_revision_hourmeter": (
                float(item["last_revision_hourmeter"])
                if item["last_revision_hourmeter"] is not None
                else None
            ),
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
        }
    
class MachineDetailSerializer(MachineListSerializer):
    class Meta(MachineListSerializer.Meta):
        fields = MachineListSerializer.Meta.fields + [
            "fazenda",
            "location_text",
            "is_active",
            "created_at",
            "updated_at",
        ]


class HourmeterReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourmeterReading
        fields = [
            "id",
            "machine",
            "value",
            "measured_at",
            "source",
            "notes",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class CreateHourmeterReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourmeterReading
        fields = [
            "value",
            "measured_at",
            "source",
            "notes",
        ]


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    maintenance_type_label = serializers.CharField(
        source="get_maintenance_type_display",
        read_only=True,
    )
    maintenance_plan_name = serializers.CharField(
        source="maintenance_plan.name",
        read_only=True,
    )

    class Meta:
        model = MaintenanceRecord
        fields = [
            "id",
            "machine",
            "maintenance_plan",
            "maintenance_plan_name",
            "maintenance_type",
            "maintenance_type_label",
            "performed_at",
            "hourmeter",
            "description",
            "next_revision_hourmeter",
            "created_at",
        ]
        read_only_fields = ["created_at", "next_revision_hourmeter"]

class MachineAlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineAlertRule
        fields = [
            "id",
            "machine",
            "managers",
            "enabled",
            "hours_before",
            "days_before",
            "notify_when_overdue",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

class MaintenancePlanSerializer(serializers.ModelSerializer):
    farms_names = serializers.SerializerMethodField()
    machine_types_labels = serializers.SerializerMethodField()

    class Meta:
        model = MaintenancePlan
        fields = [
            "id",
            "name",
            "farms",
            "farms_names",
            "machine_types",
            "machine_types_labels",
            "interval_hours",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_farms_names(self, obj):
        return [str(farm) for farm in obj.farms.all()]

    def get_machine_types_labels(self, obj):
        if not obj.machine_types:
            return ["Todos"]

        labels = dict(MaintenancePlan.MachineType.choices)

        return [
            labels.get(machine_type, machine_type)
            for machine_type in obj.machine_types
        ]