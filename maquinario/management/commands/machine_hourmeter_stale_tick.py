from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone

from maquinario.models import (
    Machine,
    MachineHourmeterStaleAlertDispatch,
)
from opscheckin.models import Manager, OutboundMessage
from opscheckin.services.whatsapp import send_template


MACHINE_HOURMETER_STALE_ALERT_CODE = "machine_hourmeter_stale_alert"
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
        dry_run = bool(options["dry_run"])

        today = timezone.localdate()
        now = timezone.now()
        cutoff_date = today - timedelta(days=days)

        machines = (
            Machine.objects
            .select_related("fazenda")
            .filter(
                is_active=True,
                status=Machine.Status.OPERATION,
                current_hourmeter__gt=0,
                last_hourmeter_at__isnull=False,
                last_hourmeter_at__date__lte=cutoff_date,
            )
            .order_by("fazenda_id", "identifier")
        )

        sent = 0
        skipped = 0
        dry_run_update_manager_count = 0
        dry_run_field_manager_count = 0
        machines_count = 0

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN ativo: nenhuma mensagem será enviada e nenhum dispatch será criado."
                )
            )
            self.stdout.write(
                f"Critério: máquinas em operação com última atualização em {cutoff_date} ou antes."
            )
            self.stdout.write("")

        for machine in machines:
            machines_count += 1

            last_update_label = format_last_update(machine, today)
            current_hourmeter = format_decimal_br(machine.current_hourmeter)
            machine_label = f"{machine.identifier} - {machine.description}"

            update_managers = (
                Manager.objects
                .filter(
                    is_active=True,
                    projeto__fazenda_id=machine.fazenda_id,
                    notification_subscriptions__notification_type__code=MACHINE_HOURMETER_STALE_ALERT_CODE,
                    notification_subscriptions__notification_type__is_active=True,
                    notification_subscriptions__is_active=True,
                )
                .exclude(
                    division__name__iexact=FIELD_MANAGER_DIVISION_NAME,
                )
                .distinct()
                .order_by("name")
            )    

            field_managers = (
                Manager.objects
                .filter(
                    is_active=True,
                    projeto__fazenda_id=machine.fazenda_id,
                    division__name__iexact=FIELD_MANAGER_DIVISION_NAME,
                    notification_subscriptions__notification_type__code=MACHINE_HOURMETER_STALE_ALERT_CODE,
                    notification_subscriptions__notification_type__is_active=True,
                    notification_subscriptions__is_active=True,
                )
                .distinct()
                .order_by("name")
            )

            if dry_run:
                self.stdout.write(
                    self.style.NOTICE(
                        f"[MÁQUINA] {machine.fazenda} | {machine_label} | "
                        f"horímetro={current_hourmeter}h | última={last_update_label}"
                    )
                )

            for manager in update_managers:
                body_text = (
                    f"Atualização de horímetro pendente | "
                    f"{machine.fazenda} | {machine.identifier} | "
                    f"última atualização: {last_update_label}"
                )

                if dry_run:
                    dry_run_update_manager_count += 1
                    self.stdout.write(
                        f"  [UPDATE_MANAGER] "
                        f"{manager.name} | {manager.phone_e164} | "
                        f"template=machine_hourmeter_stale_update_request | "
                        f"params=[{machine.fazenda}, {machine_label}, {current_hourmeter}, "
                        f"{last_update_label}, {machine.identifier}]"
                    )
                    continue

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

                try:
                    resp = send_template(
                        manager.phone_e164,
                        template_name="machine_hourmeter_stale_update_request",
                        body_params=[
                            str(machine.fazenda),
                            machine_label,
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
                    self.stderr.write(
                        f"Erro ao enviar update request para {manager}: {exc}"
                    )

            for manager in field_managers:
                body_text = (
                    f"Aviso gerente de campo | horímetro desatualizado | "
                    f"{machine.fazenda} | {machine.identifier} | "
                    f"última atualização: {last_update_label}"
                )

                if dry_run:
                    dry_run_field_manager_count += 1
                    self.stdout.write(
                        f"  [FIELD_MANAGER] "
                        f"{manager.name} | {manager.phone_e164} | "
                        f"template=machine_hourmeter_stale_field_manager_notice | "
                        f"params=[{machine.fazenda}, {machine_label}, {last_update_label}]"
                    )
                    continue

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

                try:
                    resp = send_template(
                        manager.phone_e164,
                        template_name="machine_hourmeter_stale_field_manager_notice",
                        body_params=[
                            str(machine.fazenda),
                            machine_label,
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
                    self.stderr.write(
                        f"Erro ao enviar field manager notice para {manager}: {exc}"
                    )

            if dry_run:
                self.stdout.write("")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "machine_hourmeter_stale_tick DRY-RUN finalizado. "
                    f"maquinas={machines_count} "
                    f"update_manager_msgs={dry_run_update_manager_count} "
                    f"field_manager_msgs={dry_run_field_manager_count} "
                    f"dispatches_criados=0 enviados=0"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"machine_hourmeter_stale_tick finalizado. enviados={sent} ignorados={skipped}"
            )
        )