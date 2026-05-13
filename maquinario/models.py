from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

class Machine(models.Model):
    class MachineType(models.TextChoices):
        TRACTOR = "tractor", "Trator"
        SPRAYER = "sprayer", "Pulverizador"
        HARVESTER = "harvester", "Colheitadeira"
        OTHER = "other", "Outro"

    class Status(models.TextChoices):
        OPERATION = "operation", "Em operação"
        MAINTENANCE = "maintenance", "Manutenção"
        REVISION = "revision", "Revisão"
        INACTIVE = "inactive", "Inativo"

    fazenda = models.ForeignKey(
        "diamante.Fazenda",
        on_delete=models.PROTECT,
        related_name="machines",
    )

    identifier = models.CharField(
        "Identificador",
        max_length=80,
        help_text="Código interno da máquina. Ex: TR23, 11-0038.",
    )

    chassis = models.CharField(
        "Chassi",
        max_length=120,
        blank=True,
        null=True,
    )

    description = models.CharField(
        "Descrição",
        max_length=180,
    )

    machine_type = models.CharField(
        "Tipo",
        max_length=30,
        choices=MachineType.choices,
        default=MachineType.TRACTOR,
    )

    brand = models.CharField(
        "Marca",
        max_length=80,
        blank=True,
        null=True,
    )

    model_name = models.CharField(
        "Modelo",
        max_length=80,
        blank=True,
        null=True,
    )

    status = models.CharField(
        "Status",
        max_length=30,
        choices=Status.choices,
        default=Status.OPERATION,
    )

    current_hourmeter = models.DecimalField(
        "Horímetro atual",
        max_digits=10,
        decimal_places=1,
        default=Decimal("0.0"),
    )

    last_hourmeter_at = models.DateTimeField(
        "Última leitura do horímetro",
        blank=True,
        null=True,
    )

    last_revision_hourmeter = models.DecimalField(
        "Horímetro da última revisão",
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    next_revision_hourmeter = models.DecimalField(
        "Horímetro da próxima revisão",
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    revision_interval_hours = models.DecimalField(
        "Intervalo padrão entre revisões",
        max_digits=8,
        decimal_places=1,
        default=Decimal("250.0"),
        help_text="Ex: revisão a cada 250 horas.",
    )

    average_hours_per_day = models.DecimalField(
        "Média de horas por dia",
        max_digits=8,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Média estimada de trabalho por dia. Usado para calcular dias até a próxima revisão.",
    )

    location_text = models.CharField(
        "Localidade original",
        max_length=180,
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        "Ativa",
        default=True,
    )

    created_at = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Máquina"
        verbose_name_plural = "Máquinas"
        ordering = ["identifier"]
        constraints = [
            models.UniqueConstraint(
                fields=["fazenda", "identifier"],
                name="unique_machine_identifier_per_farm",
            )
        ]

    def __str__(self):
        return f"{self.identifier} - {self.description}"
    
    def get_applicable_maintenance_plans(self):
        plans = (
            MaintenancePlan.objects
            .filter(
                is_active=True,
                farms=self.fazenda,
            )
            .distinct()
            .order_by("interval_hours", "name")
        )

        applicable = []

        for plan in plans:
            if plan.applies_to_machine(self):
                applicable.append(plan)

        return applicable

    def get_maintenance_summary(self):
        summary = []

        plans = self.get_applicable_maintenance_plans()

        for plan in plans:
            last_record = (
                self.maintenance_records
                .filter(maintenance_plan=plan)
                .order_by("-hourmeter", "-performed_at", "-id")
                .first()
            )

            if last_record:
                last_hourmeter = last_record.hourmeter
                next_hourmeter = last_record.next_revision_hourmeter or (
                    last_record.hourmeter + plan.interval_hours
                )
                last_performed_at = last_record.performed_at
                record_id = last_record.id
            else:
                last_hourmeter = None
                next_hourmeter = plan.interval_hours
                last_performed_at = None
                record_id = None

            hours_to_next = None

            if next_hourmeter is not None:
                hours_to_next = max(next_hourmeter - self.current_hourmeter, Decimal("0.0"))

            summary.append({
                "plan_id": plan.id,
                "plan_name": plan.name,
                "interval_hours": plan.interval_hours,
                "last_record_id": record_id,
                "last_revision_hourmeter": last_hourmeter,
                "last_revision_at": last_performed_at,
                "next_revision_hourmeter": next_hourmeter,
                "hours_to_next_revision": hours_to_next,
                "is_due": hours_to_next is not None and hours_to_next <= 0,
            })

        return summary

    def get_next_due_maintenance_item(self):
        summary = self.get_maintenance_summary()

        valid_items = [
            item for item in summary
            if item.get("next_revision_hourmeter") is not None
        ]

        if not valid_items:
            return None

        return sorted(
            valid_items,
            key=lambda item: item["next_revision_hourmeter"]
        )[0]

    @property
    def hours_to_next_revision(self):
        if self.next_revision_hourmeter is None:
            return None

        remaining = self.next_revision_hourmeter - self.current_hourmeter
        return max(remaining, Decimal("0.0"))

    @property
    def estimated_days_to_next_revision(self):
        if self.hours_to_next_revision is None:
            return None

        if not self.average_hours_per_day or self.average_hours_per_day <= 0:
            return None

        return int((self.hours_to_next_revision / self.average_hours_per_day).to_integral_value(rounding="ROUND_CEILING"))

    @property
    def revision_progress_percent(self):
        if self.last_revision_hourmeter is None or self.next_revision_hourmeter is None:
            return None

        total_range = self.next_revision_hourmeter - self.last_revision_hourmeter
        if total_range <= 0:
            return None

        used = self.current_hourmeter - self.last_revision_hourmeter
        percent = (used / total_range) * Decimal("100")

        if percent < 0:
            return 0

        if percent > 100:
            return 100

        return int(percent)


class HourmeterReading(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        API = "api", "API"
        IMPORT = "import", "Importação"
        APP = "app", "Aplicativo"
        APP_OFFLINE = "app_offline", "Aplicativo offline"
        WHATSAPP = "whatsapp", "WhatsApp"

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="hourmeter_readings",
    )

    value = models.DecimalField(
        "Horímetro",
        max_digits=10,
        decimal_places=1,
    )

    measured_at = models.DateTimeField(
        "Data da leitura",
        default=timezone.now,
    )

    source = models.CharField(
        "Origem",
        max_length=30,
        choices=Source.choices,
        default=Source.MANUAL,
    )

    notes = models.TextField(
        "Observações",
        blank=True,
        null=True,
    )
    
    user_uid = models.CharField(
        "UID do usuário",
        max_length=180,
        blank=True,
    )

    user_email = models.EmailField(
        "E-mail do usuário",
        blank=True,
    )

    user_display_name = models.CharField(
        "Nome do usuário",
        max_length=180,
        blank=True,
    )

    created_at = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Leitura de horímetro"
        verbose_name_plural = "Leituras de horímetro"
        ordering = ["-measured_at", "-id"]
        indexes = [
            models.Index(fields=["machine", "-measured_at"]),
        ]

    def __str__(self):
        return f"{self.machine.identifier} - {self.value}h"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        machine = self.machine

        should_update_machine = (
            machine.last_hourmeter_at is None
            or self.measured_at >= machine.last_hourmeter_at
        )

        if should_update_machine:
            machine.current_hourmeter = self.value
            machine.last_hourmeter_at = self.measured_at
            machine.save(
                update_fields=[
                    "current_hourmeter",
                    "last_hourmeter_at",
                    "updated_at",
                ]
            )




class MaintenancePlan(models.Model):
    class MachineType(models.TextChoices):
        TRACTOR = "tractor", "Trator"
        SPRAYER = "sprayer", "Pulverizador"
        HARVESTER = "harvester", "Colheitadeira"
        OTHER = "other", "Outro"

    name = models.CharField(
        "Nome da revisão",
        max_length=120,
        help_text="Ex: Revisão de 300h, Revisão de 600h.",
    )

    farms = models.ManyToManyField(
        "diamante.Fazenda",
        related_name="maintenance_plans",
        blank=True,
        verbose_name="Fazendas",
        help_text="Fazendas onde essa regra de manutenção pode ser aplicada.",
    )

    machine_types = models.JSONField(
        "Tipos de máquina",
        default=list,
        blank=True,
        help_text="Lista de tipos: tractor, sprayer, harvester, other.",
    )

    interval_hours = models.DecimalField(
        "Intervalo em horas",
        max_digits=8,
        decimal_places=1,
        help_text="Ex: 300, 600.",
    )

    description = models.TextField(
        "Descrição padrão",
        blank=True,
        null=True,
        help_text="O que deve ser verificado/trocado nessa revisão.",
    )

    is_active = models.BooleanField(
        "Ativo",
        default=True,
    )

    created_at = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Plano de manutenção"
        verbose_name_plural = "Planos de manutenção"
        ordering = ["interval_hours", "name"]

    def __str__(self):
        return f"{self.name} - {self.interval_hours}h"

    def applies_to_machine(self, machine):
        if not self.is_active:
            return False

        has_farm = self.farms.filter(id=machine.fazenda_id).exists()

        # Se não selecionar nenhum tipo, aplica para todos
        selected_machine_types = self.machine_types or []
        has_type = not selected_machine_types or machine.machine_type in selected_machine_types

        return has_farm and has_type


class MaintenanceRecord(models.Model):
    class MaintenanceType(models.TextChoices):
        REVISION = "revision", "Revisão"
        CORRECTIVE = "corrective", "Corretiva"
        PREVENTIVE = "preventive", "Preventiva"
        OTHER = "other", "Outra"

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="maintenance_records",
    )

    maintenance_plan = models.ForeignKey(
        MaintenancePlan,
        on_delete=models.SET_NULL,
        related_name="maintenance_records",
        blank=True,
        null=True,
        verbose_name="Plano de manutenção",
    )

    maintenance_type = models.CharField(
        "Tipo",
        max_length=30,
        choices=MaintenanceType.choices,
        default=MaintenanceType.REVISION,
    )

    performed_at = models.DateTimeField(
        "Realizada em",
        default=timezone.now,
    )

    hourmeter = models.DecimalField(
        "Horímetro da revisão",
        max_digits=10,
        decimal_places=1,
    )

    description = models.TextField(
        "Descrição",
        blank=True,
        null=True,
    )

    next_revision_hourmeter = models.DecimalField(
        "Próxima revisão no horímetro",
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )
    
    user_uid = models.CharField(
        "UID do usuário",
        max_length=180,
        blank=True,
    )

    user_email = models.EmailField(
        "E-mail do usuário",
        blank=True,
    )

    user_display_name = models.CharField(
        "Nome do usuário",
        max_length=180,
        blank=True,
    )

    created_at = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Manutenção/Revisão"
        verbose_name_plural = "Manutenções/Revisões"
        ordering = ["-performed_at", "-id"]

    def __str__(self):
        return f"{self.machine.identifier} - {self.get_maintenance_type_display()}"

    def save(self, *args, **kwargs):
        if self.maintenance_plan and not self.maintenance_plan.applies_to_machine(self.machine):
            raise ValidationError("Este plano de manutenção não se aplica a essa máquina.")

        interval_hours = self.machine.revision_interval_hours

        if self.maintenance_plan and self.maintenance_plan.interval_hours:
            interval_hours = self.maintenance_plan.interval_hours

        if self.next_revision_hourmeter is None:
            self.next_revision_hourmeter = self.hourmeter + interval_hours

        if not self.description and self.maintenance_plan:
            self.description = self.maintenance_plan.description

        super().save(*args, **kwargs)

        machine = self.machine
        next_due = machine.get_next_due_maintenance_item()

        machine.last_revision_hourmeter = self.hourmeter

        if next_due:
            machine.next_revision_hourmeter = next_due["next_revision_hourmeter"]
        else:
            machine.next_revision_hourmeter = self.next_revision_hourmeter
        machine.status = Machine.Status.OPERATION

        if machine.current_hourmeter < self.hourmeter:
            machine.current_hourmeter = self.hourmeter
            machine.last_hourmeter_at = self.performed_at

        machine.save(
            update_fields=[
                "last_revision_hourmeter",
                "next_revision_hourmeter",
                "current_hourmeter",
                "last_hourmeter_at",
                "status",
                "updated_at",
            ]
        )
    
class MachineAlertRule(models.Model):
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )

    managers = models.ManyToManyField(
        "opscheckin.Manager",
        blank=True,
        related_name="machine_alert_rules",
    )

    enabled = models.BooleanField(
        "Ativa",
        default=True,
    )

    hours_before = models.DecimalField(
        "Alertar faltando quantas horas",
        max_digits=8,
        decimal_places=1,
        default=Decimal("30.0"),
    )

    days_before = models.PositiveIntegerField(
        "Alertar faltando quantos dias",
        default=7,
    )

    notify_when_overdue = models.BooleanField(
        "Avisar quando vencida",
        default=True,
    )

    created_at = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Regra de alerta"
        verbose_name_plural = "Regras de alerta"

    def __str__(self):
        return f"Alerta - {self.machine.identifier}"
    



class MachineFarmTransfer(models.Model):
    class Source(models.TextChoices):
        APP = "app", "Aplicativo"
        ADMIN = "admin", "Admin"
        AGENT = "agent", "Agente"
        SYSTEM = "system", "Sistema"

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="farm_transfers",
    )

    from_fazenda = models.ForeignKey(
        "diamante.Fazenda",
        on_delete=models.PROTECT,
        related_name="machine_transfers_from",
        null=True,
        blank=True,
    )

    to_fazenda = models.ForeignKey(
        "diamante.Fazenda",
        on_delete=models.PROTECT,
        related_name="machine_transfers_to",
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.APP,
    )

    notes = models.TextField(blank=True)

    user_uid = models.CharField(max_length=180, blank=True)
    user_email = models.EmailField(blank=True)
    user_display_name = models.CharField(max_length=180, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transferência de Fazenda"
        verbose_name_plural = "Transferências de Fazenda"

    def __str__(self):
        return f"{self.machine} → {self.to_fazenda}"