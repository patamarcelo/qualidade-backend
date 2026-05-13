from django.contrib import admin

from .models import (
    Machine,
    HourmeterReading,
    MaintenanceRecord,
    MachineAlertRule,
    MaintenancePlan,
    MachineFarmTransfer,
    MachineStatusChange
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

    machines = queryset.select_related("fazenda").prefetch_related(
        "maintenance_records",
        "maintenance_records__maintenance_plan",
    )

    plans = (
        MaintenancePlan.objects
        .filter(is_active=True)
        .prefetch_related("farms")
        .order_by("interval_hours", "name")
    )

    base_headers = [
        "ID",
        "Fazenda",
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
        "Ativa",
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
            machine.id,
            str(machine.fazenda),
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
            "Sim" if machine.is_active else "Não",
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
        "maintenance_plan",
        "maintenance_type",
        "performed_at",
        "hourmeter",
        "next_revision_hourmeter",
        "description",
    ]
    readonly_fields = [
        "next_revision_hourmeter",
    ]
    autocomplete_fields = [
        "maintenance_plan",
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
        "next_due_plan_display",
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
        "next_due_plan_display",
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
                "next_due_plan_display",
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
        next_due = obj.get_next_due_maintenance_item()

        if next_due and next_due.get("hours_to_next_revision") is not None:
            return f'{next_due["hours_to_next_revision"]} h'

        value = obj.hours_to_next_revision
        if value is None:
            return "-"

        return f"{value} h"

    hours_to_next_revision_display.short_description = "Horas até próxima revisão"


    def estimated_days_to_next_revision_display(self, obj):
        next_due = obj.get_next_due_maintenance_item()

        if next_due and next_due.get("hours_to_next_revision") is not None:
            hours_to_next = next_due["hours_to_next_revision"]

            if obj.average_hours_per_day and obj.average_hours_per_day > 0:
                days = int(
                    (hours_to_next / obj.average_hours_per_day)
                    .to_integral_value(rounding="ROUND_CEILING")
                )
                return f"{days} dias"

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
    
    
    def next_due_plan_display(self, obj):
        next_due = obj.get_next_due_maintenance_item()

        if not next_due:
            return "-"

        plan_name = next_due.get("plan_name") or "-"
        next_hourmeter = next_due.get("next_revision_hourmeter")
        hours_to_next = next_due.get("hours_to_next_revision")

        if next_hourmeter is None:
            return plan_name

        return f"{plan_name} em {next_hourmeter}h | faltam {hours_to_next}h"

    next_due_plan_display.short_description = "Próxima manutenção"


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
        "maintenance_plan",
        "machine__fazenda",
        "performed_at",
    ]

    search_fields = [
        "machine__identifier",
        "machine__description",
        "maintenance_plan__name",
        "description",
    ]

    autocomplete_fields = [
        "machine",
        "maintenance_plan",
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
    


@admin.register(MachineFarmTransfer)
class MachineFarmTransferAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "machine_display",
        "from_fazenda",
        "to_fazenda",
        "source_badge",
        "user_display",
        "created_at",
    ]

    list_filter = [
        "source",
        "from_fazenda",
        "to_fazenda",
        "created_at",
    ]

    search_fields = [
        "machine__identifier",
        "machine__description",
        "machine__chassis",
        "from_fazenda__nome",
        "to_fazenda__nome",
        "user_email",
        "user_display_name",
        "user_uid",
        "notes",
    ]

    readonly_fields = [
        "machine",
        "from_fazenda",
        "to_fazenda",
        "source",
        "notes",
        "user_uid",
        "user_email",
        "user_display_name",
        "created_at",
    ]

    date_hierarchy = "created_at"

    ordering = ["-created_at"]

    list_select_related = [
        "machine",
        "from_fazenda",
        "to_fazenda",
    ]

    fieldsets = (
        (
            "Transferência",
            {
                "fields": (
                    "machine",
                    "from_fazenda",
                    "to_fazenda",
                    "source",
                    "notes",
                )
            },
        ),
        (
            "Usuário",
            {
                "fields": (
                    "user_display_name",
                    "user_email",
                    "user_uid",
                )
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def machine_display(self, obj):
        identifier = getattr(obj.machine, "identifier", None) or "Sem código"
        description = getattr(obj.machine, "description", None) or ""

        if description:
            return f"{identifier} - {description}"

        return identifier

    machine_display.short_description = "Máquina"
    machine_display.admin_order_field = "machine__identifier"

    def user_display(self, obj):
        if obj.user_display_name and obj.user_email:
            return f"{obj.user_display_name} ({obj.user_email})"

        if obj.user_display_name:
            return obj.user_display_name

        if obj.user_email:
            return obj.user_email

        if obj.user_uid:
            return obj.user_uid

        return "-"

    user_display.short_description = "Usuário"

    def source_badge(self, obj):
        labels = {
            "app": "Aplicativo",
            "admin": "Admin",
            "agent": "Agente",
            "system": "Sistema",
        }

        return labels.get(obj.source, obj.source or "-")

    source_badge.short_description = "Origem"




@admin.register(MachineStatusChange)
class MachineStatusChangeAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "machine_display",
        "from_status",
        "to_status",
        "source",
        "user_display",
        "created_at",
    ]

    list_filter = [
        "from_status",
        "to_status",
        "source",
        "created_at",
    ]

    search_fields = [
        "machine__identifier",
        "machine__description",
        "user_email",
        "user_display_name",
        "user_uid",
        "notes",
    ]

    readonly_fields = [
        "machine",
        "from_status",
        "to_status",
        "source",
        "notes",
        "user_uid",
        "user_email",
        "user_display_name",
        "created_at",
    ]

    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["machine"]

    fieldsets = (
        (
            "Alteração",
            {
                "fields": (
                    "machine",
                    "from_status",
                    "to_status",
                    "source",
                    "notes",
                )
            },
        ),
        (
            "Usuário",
            {
                "fields": (
                    "user_display_name",
                    "user_email",
                    "user_uid",
                )
            },
        ),
        (
            "Controle",
            {
                "fields": ("created_at",)
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def machine_display(self, obj):
        identifier = getattr(obj.machine, "identifier", None) or "Sem código"
        description = getattr(obj.machine, "description", None) or ""

        if description:
            return f"{identifier} - {description}"

        return identifier

    machine_display.short_description = "Máquina"

    def user_display(self, obj):
        if obj.user_display_name and obj.user_email:
            return f"{obj.user_display_name} ({obj.user_email})"

        if obj.user_display_name:
            return obj.user_display_name

        if obj.user_email:
            return obj.user_email

        if obj.user_uid:
            return obj.user_uid

        return "-"

    user_display.short_description = "Usuário"