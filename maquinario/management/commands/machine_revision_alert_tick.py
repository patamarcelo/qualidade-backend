from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import IntegrityError

from maquinario.models import (
    Machine,
    MachineMaintenanceAlertDispatch,
)
from opscheckin.models import Manager, OutboundMessage
from opscheckin.services.whatsapp import send_template


DEFAULT_HOURS_THRESHOLD = Decimal("50.0")
UPDATE_MACHINE_CODE = "update_machine"
MACHINE_REVISION_ALERT_TEMPLATE = "machine_revision_alert"

def extract_provider_message_id(resp):
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""
    
    
def format_decimal_br(value):
    if value is None:
        return "-"

    value = Decimal(str(value))
    text = f"{value:,.1f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def manager_can_update_machine(manager):
    return manager.notification_subscriptions.filter(
        notification_type__code=UPDATE_MACHINE_CODE,
        notification_type__is_active=True,
        is_active=True,
    ).exists()


class Command(BaseCommand):
    help = "Envia alertas diários de revisões próximas das máquinas."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=str, default="50")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        threshold = Decimal(str(options["hours"]).replace(",", "."))
        dry_run = options["dry_run"]

        today = timezone.localdate()
        now = timezone.now()

        machines = (
            Machine.objects
            .select_related("fazenda")
            .filter(
                is_active=True,
                status=Machine.Status.OPERATION,
            )
            .order_by("fazenda_id", "identifier")
        )

        sent = 0
        skipped = 0

        for machine in machines:
            summary = machine.get_maintenance_summary()

            due_items = [
                item for item in summary
                if item.get("hours_to_next_revision") is not None
                and item["hours_to_next_revision"] <= threshold
            ]

            if not due_items:
                continue

            managers = (
                Manager.objects
                .filter(
                    is_active=True,
                    projeto__fazenda_id=machine.fazenda_id,
                    notification_subscriptions__notification_type__code=UPDATE_MACHINE_CODE,
                    notification_subscriptions__notification_type__is_active=True,
                    notification_subscriptions__is_active=True,
                )
                .distinct()
                .order_by("name")
            )

            for manager in managers:
                for item in due_items:
                    try:
                        dispatch, created = MachineMaintenanceAlertDispatch.objects.get_or_create(
                            manager=manager,
                            machine=machine,
                            maintenance_plan_id=item.get("plan_id"),
                            reference_date=today,
                            defaults={
                                "hours_to_next_revision": item["hours_to_next_revision"],
                            },
                        )
                    except IntegrityError:
                        skipped += 1
                        continue

                    if not created:
                        skipped += 1
                        continue

                    current_hourmeter = format_decimal_br(machine.current_hourmeter)
                    next_hourmeter = format_decimal_br(item["next_revision_hourmeter"])
                    hours_remaining = format_decimal_br(item["hours_to_next_revision"])
                    plan_name = str(item.get("plan_name") or "Revisão programada")
                    machine_label = f"{machine.identifier} - {machine.description}"

                    body_text = (
                        f"Revisão próxima | "
                        f"{machine.fazenda} | {machine.identifier} | "
                        f"{plan_name} | faltam {hours_remaining}h"
                    )

                    if dry_run:
                        self.stdout.write(
                            "[REVISION_ALERT] "
                            f"{manager.phone_e164} | "
                            f"fazenda={machine.fazenda} | "
                            f"machine={machine_label} | "
                            f"current={current_hourmeter} | "
                            f"plan={plan_name} | "
                            f"next={next_hourmeter} | "
                            f"remaining={hours_remaining}"
                        )
                        continue

                    try:
                        resp = send_template(
                            manager.phone_e164,
                            template_name=MACHINE_REVISION_ALERT_TEMPLATE,
                            body_params=[
                                str(machine.fazenda),
                                machine_label,
                                current_hourmeter,
                                plan_name,
                                next_hourmeter,
                                hours_remaining,
                            ],
                        )

                        provider_id = extract_provider_message_id(resp)

                        dispatch.sent_at = now
                        dispatch.provider_message_id = provider_id
                        dispatch.save(update_fields=["sent_at", "provider_message_id"])

                        OutboundMessage.objects.create(
                            manager=manager,
                            to_phone=manager.phone_e164,
                            provider_message_id=provider_id,
                            kind="machine_revision_alert",
                            text=body_text,
                            sent_at=now,
                            raw_response=resp,
                            wa_status="sent" if provider_id else "",
                            wa_sent_at=now if provider_id else None,
                        )

                        sent += 1

                    except Exception as exc:
                        self.stderr.write(
                            f"Erro ao enviar alerta de revisão para {manager}: {exc}"
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"machine_revision_alert_tick finalizado. enviados={sent} ignorados={skipped}"
            )
        )