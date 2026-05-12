from django.contrib import admin

from .models import (
    Machine,
    HourmeterReading,
    MaintenanceRecord,
    MachineAlertRule,
    MaintenancePlan,
)

from django.http import HttpResponse
from openpyxl import Workbook

from django import forms


class MaintenancePlanAdminForm(forms.ModelForm):
    machine_types = forms.MultipleChoiceField(
        label="Tipos de máquina",
        choices=MaintenancePlan.MachineType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Se não marcar nenhum tipo, o plano será aplicado para todos os tipos de máquina.",
    )

    class Meta:
        model = MaintenancePlan
        fields = "__all__"

    def clean_machine_types(self):
        return self.cleaned_data.get("machine_types") or []


@admin.action(description="Exportar relatório de máquinas em Excel")
def export_machines_excel(modeladmin, request, queryset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Máquinas"

    headers = [
        "ID",
        "Fazenda",
        "Identificador",
        "Descrição",
        "Chassi",
        "Tipo",
        "Status",
        "Horímetro atual",
        "Última leitura",
        "Última revisão",
        "Próxima revisão",
        "Horas restantes",
        "Dias estimados",
        "Progresso revisão (%)",
        "Ativa",
    ]

    ws.append(headers)

    for machine in queryset.select_related("fazenda"):
        ws.append([
            machine.id,
            str(machine.fazenda),
            machine.identifier,
            machine.description,
            machine.chassis or "",
            machine.get_machine_type_display(),
            machine.get_status_display(),
            float(machine.current_hourmeter or 0),
            machine.last_hourmeter_at.strftime("%d/%m/%Y %H:%M") if machine.last_hourmeter_at else "",
            float(machine.last_revision_hourmeter or 0) if machine.last_revision_hourmeter is not None else "",
            float(machine.next_revision_hourmeter or 0) if machine.next_revision_hourmeter is not None else "",
            float(machine.hours_to_next_revision or 0) if machine.hours_to_next_revision is not None else "",
            machine.estimated_days_to_next_revision or "",
            machine.revision_progress_percent or "",
            "Sim" if machine.is_active else "Não",
        ])

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
    actions = [export_machines_excel]
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
        "maintenance_plan",
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
    

@admin.register(MaintenancePlan)
class MaintenancePlanAdmin(admin.ModelAdmin):
    form = MaintenancePlanAdminForm

    list_display = [
        "name",
        "interval_hours",
        "machine_types_display",
        "farms_display",
        "is_active",
    ]

    list_filter = [
        "is_active",
        "farms",
    ]

    search_fields = [
        "name",
        "description",
    ]

    filter_horizontal = [
        "farms",
    ]

    ordering = [
        "interval_hours",
        "name",
    ]

    def farms_display(self, obj):
        return ", ".join(str(farm) for farm in obj.farms.all())

    farms_display.short_description = "Fazendas"

    def machine_types_display(self, obj):
        if not obj.machine_types:
            return "Todos"

        labels = dict(MaintenancePlan.MachineType.choices)

        return ", ".join(
            labels.get(machine_type, machine_type)
            for machine_type in obj.machine_types
        )

    machine_types_display.short_description = "Tipos de máquina"