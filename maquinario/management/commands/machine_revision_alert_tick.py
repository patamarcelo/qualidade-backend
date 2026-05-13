from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import IntegrityError

from maquinario.models import (
    Machine,
    MachineMaintenanceAlertDispatch,
)
from opscheckin.models import Manager, OutboundMessage
from opscheckin.services.whatsapp import send_text


DEFAULT_HOURS_THRESHOLD = Decimal("50.0")
UPDATE_MACHINE_CODE = "update_machine"


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
                lines = [
                    f"⚠️ Revisão próxima - {machine.identifier}",
                    "",
                    f"Fazenda: {machine.fazenda}",
                    f"Máquina: {machine.description}",
                    f"Horímetro atual: {format_decimal_br(machine.current_hourmeter)}h",
                    "",
                    "Revisões próximas:",
                ]

                for item in due_items:
                    hours = format_decimal_br(item["hours_to_next_revision"])
                    next_hourmeter = format_decimal_br(item["next_revision_hourmeter"])

                    lines.append(
                        f"• {item['plan_name']}: próxima em {next_hourmeter}h "
                        f"(faltam {hours}h)"
                    )

                lines.extend([
                    "",
                    "Para atualizar:",
                    f"HM {machine.identifier} {format_decimal_br(machine.current_hourmeter)}",
                    "",
                    "Para registrar revisão:",
                    f"REV {machine.identifier} 300 {format_decimal_br(machine.current_hourmeter)}",
                ])

                body = "\n".join(lines)

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

                    if dry_run:
                        self.stdout.write(body)
                        continue

                    try:
                        resp = send_text(manager.phone_e164, body)

                        provider_id = ""
                        try:
                            provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
                        except Exception:
                            provider_id = ""

                        dispatch.sent_at = now
                        dispatch.provider_message_id = provider_id
                        dispatch.save(update_fields=["sent_at", "provider_message_id"])

                        OutboundMessage.objects.create(
                            manager=manager,
                            to_phone=manager.phone_e164,
                            provider_message_id=provider_id,
                            kind="machine_revision_alert",
                            text=body,
                            sent_at=now,
                            raw_response=resp,
                            wa_status="sent" if provider_id else "",
                            wa_sent_at=now if provider_id else None,
                        )

                        sent += 1

                    except Exception as exc:
                        self.stderr.write(
                            f"Erro ao enviar para {manager}: {exc}"
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"machine_revision_alert_tick finalizado. enviados={sent} ignorados={skipped}"
            )
        )