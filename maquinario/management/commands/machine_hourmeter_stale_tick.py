from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from maquinario.models import (
    Machine,
    MachineHourmeterStaleAlertDispatch,
)
from opscheckin.models import Manager, OutboundMessage
from opscheckin.services.whatsapp import send_template


UPDATE_MACHINE_CODE = "update_machine"
FIELD_MANAGER_DIVISION_NAME = "Gerente de Campo"


def format_decimal_br(value):
    if value is None:
        return "-"

    value = Decimal(str(value))
    text = f"{value:,.1f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def extract_provider_message_id(resp):
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""


def format_last_update(machine, today):
    if not machine.last_hourmeter_at:
        return "sem registro"

    local_dt = timezone.localtime(machine.last_hourmeter_at)
    days = (today - local_dt.date()).days

    if days <= 0:
        return "hoje"

    if days == 1:
        return "há 1 dia"

    return f"há {days} dias"


class Command(BaseCommand):
    help = "Envia alertas de máquinas em operação sem atualização recente de horímetro."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=4)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = int(options["days"])
        dry_run = options["dry_run"]

        today = timezone.localdate()
        now = timezone.now()
        cutoff = now - timedelta(days=days)

        machines = (
            Machine.objects
            .select_related("fazenda")
            .filter(
                is_active=True,
                status=Machine.Status.OPERATION,
                current_hourmeter__gt=0,
                last_hourmeter_at__isnull=False,
                last_hourmeter_at__lte=cutoff,
            )
            .order_by("fazenda_id", "identifier")
        )

        sent = 0
        skipped = 0

        for machine in machines:
            last_update_label = format_last_update(machine, today)
            current_hourmeter = format_decimal_br(machine.current_hourmeter)

            update_managers = (
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

            field_managers = (
                Manager.objects
                .filter(
                    is_active=True,
                    division__name__iexact=FIELD_MANAGER_DIVISION_NAME,
                    projeto__fazenda_id=machine.fazenda_id,
                )
                .distinct()
                .order_by("name")
            )

            for manager in update_managers:
                try:
                    dispatch, created = MachineHourmeterStaleAlertDispatch.objects.get_or_create(
                        manager=manager,
                        machine=machine,
                        audience=MachineHourmeterStaleAlertDispatch.Audience.UPDATE_MANAGER,
                        reference_date=today,
                        defaults={
                            "last_hourmeter_at": machine.last_hourmeter_at,
                            "current_hourmeter": machine.current_hourmeter,
                        },
                    )
                except IntegrityError:
                    skipped += 1
                    continue

                if not created:
                    skipped += 1
                    continue

                body_text = (
                    f"Atualização de horímetro pendente | "
                    f"{machine.fazenda} | {machine.identifier} | "
                    f"última atualização: {last_update_label}"
                )

                if dry_run:
                    self.stdout.write(f"[UPDATE_MANAGER] {manager.phone_e164} - {body_text}")
                    continue

                try:
                    resp = send_template(
                        manager.phone_e164,
                        template_name="machine_hourmeter_stale_update_request",
                        body_params=[
                            str(machine.fazenda),
                            f"{machine.identifier} - {machine.description}",
                            current_hourmeter,
                            last_update_label,
                            machine.identifier,
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
                        kind="machine_hourmeter_stale_update_request",
                        text=body_text,
                        sent_at=now,
                        raw_response=resp,
                        wa_status="sent" if provider_id else "",
                        wa_sent_at=now if provider_id else None,
                    )

                    sent += 1

                except Exception as exc:
                    self.stderr.write(f"Erro ao enviar update request para {manager}: {exc}")

            for manager in field_managers:
                try:
                    dispatch, created = MachineHourmeterStaleAlertDispatch.objects.get_or_create(
                        manager=manager,
                        machine=machine,
                        audience=MachineHourmeterStaleAlertDispatch.Audience.FIELD_MANAGER,
                        reference_date=today,
                        defaults={
                            "last_hourmeter_at": machine.last_hourmeter_at,
                            "current_hourmeter": machine.current_hourmeter,
                        },
                    )
                except IntegrityError:
                    skipped += 1
                    continue

                if not created:
                    skipped += 1
                    continue

                body_text = (
                    f"Aviso gerente de campo | horímetro desatualizado | "
                    f"{machine.fazenda} | {machine.identifier} | "
                    f"última atualização: {last_update_label}"
                )

                if dry_run:
                    self.stdout.write(f"[FIELD_MANAGER] {manager.phone_e164} - {body_text}")
                    continue

                try:
                    resp = send_template(
                        manager.phone_e164,
                        template_name="machine_hourmeter_stale_field_manager_notice",
                        body_params=[
                            str(machine.fazenda),
                            f"{machine.identifier} - {machine.description}",
                            last_update_label,
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
                        kind="machine_hourmeter_stale_field_manager_notice",
                        text=body_text,
                        sent_at=now,
                        raw_response=resp,
                        wa_status="sent" if provider_id else "",
                        wa_sent_at=now if provider_id else None,
                    )

                    sent += 1

                except Exception as exc:
                    self.stderr.write(f"Erro ao enviar field manager notice para {manager}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"machine_hourmeter_stale_tick finalizado. enviados={sent} ignorados={skipped}"
            )
        )