from django.contrib import admin

from .models import (
    Machine,
    HourmeterReading,
    MaintenanceRecord,
    MachineAlertRule,
)


class HourmeterReadingInline(admin.TabularInline):
    model = HourmeterReading
    extra = 0
    fields = [
        "value",
        "measured_at",
        "source",
        "notes",
    ]
    readonly_fields = []


class MaintenanceRecordInline(admin.TabularInline):
    model = MaintenanceRecord
    extra = 0
    fields = [
        "maintenance_type",
        "performed_at",
        "hourmeter",
        "next_revision_hourmeter",
        "description",
    ]


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = [
        "identifier",
        "description",
        "fazenda",
        "machine_type",
        "status",
        "current_hourmeter",
        "next_revision_hourmeter",
        "hours_to_next_revision_display",
        "estimated_days_to_next_revision_display",
        "is_active",
    ]

    list_filter = [
        "fazenda",
        "machine_type",
        "status",
        "is_active",
    ]

    search_fields = [
        "identifier",
        "description",
        "chassis",
        "brand",
        "model_name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "hours_to_next_revision_display",
        "estimated_days_to_next_revision_display",
        "revision_progress_percent_display",
    ]

    fieldsets = (
        ("Identificação", {
            "fields": (
                "fazenda",
                "identifier",
                "chassis",
                "description",
                "machine_type",
                "brand",
                "model_name",
                "location_text",
                "is_active",
            )
        }),
        ("Status operacional", {
            "fields": (
                "status",
                "current_hourmeter",
                "last_hourmeter_at",
            )
        }),
        ("Revisão", {
            "fields": (
                "last_revision_hourmeter",
                "next_revision_hourmeter",
                "revision_interval_hours",
                "average_hours_per_day",
                "hours_to_next_revision_display",
                "estimated_days_to_next_revision_display",
                "revision_progress_percent_display",
            )
        }),
        ("Controle", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    inlines = [
        HourmeterReadingInline,
        MaintenanceRecordInline,
    ]

    def hours_to_next_revision_display(self, obj):
        value = obj.hours_to_next_revision
        if value is None:
            return "-"

        return f"{value} h"

    hours_to_next_revision_display.short_description = "Horas até próxima revisão"

    def estimated_days_to_next_revision_display(self, obj):
        value = obj.estimated_days_to_next_revision
        if value is None:
            return "-"

        return f"{value} dias"

    estimated_days_to_next_revision_display.short_description = "Dias estimados até revisão"

    def revision_progress_percent_display(self, obj):
        value = obj.revision_progress_percent
        if value is None:
            return "-"

        return f"{value}%"

    revision_progress_percent_display.short_description = "Progresso da revisão"


@admin.register(HourmeterReading)
class HourmeterReadingAdmin(admin.ModelAdmin):
    list_display = [
        "machine",
        "value",
        "measured_at",
        "source",
        "created_at",
    ]

    list_filter = [
        "source",
        "machine__fazenda",
        "measured_at",
    ]

    search_fields = [
        "machine__identifier",
        "machine__description",
        "notes",
    ]

    autocomplete_fields = [
        "machine",
    ]


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = [
        "machine",
        "maintenance_type",
        "performed_at",
        "hourmeter",
        "next_revision_hourmeter",
    ]

    list_filter = [
        "maintenance_type",
        "machine__fazenda",
        "performed_at",
    ]

    search_fields = [
        "machine__identifier",
        "machine__description",
        "description",
    ]

    autocomplete_fields = [
        "machine",
    ]


@admin.register(MachineAlertRule)
class MachineAlertRuleAdmin(admin.ModelAdmin):
    list_display = [
        "machine",
        "enabled",
        "hours_before",
        "days_before",
        "notify_when_overdue",
    ]

    list_filter = [
        "enabled",
        "notify_when_overdue",
        "machine__fazenda",
    ]

    search_fields = [
        "machine__identifier",
        "machine__description",
    ]

    autocomplete_fields = [
        "machine",
        "managers",
    ]