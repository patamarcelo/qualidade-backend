import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from maquinario.models import (
    Machine,
    HourmeterReading,
    MaintenancePlan,
    MaintenanceRecord,
    MachineWhatsappCommand,
)

from opscheckin.models import Manager, OutboundMessage
from opscheckin.services.whatsapp import send_text, send_template

import logging
logger = logging.getLogger("opscheckin.whatsapp")


UPDATE_MACHINE_CODE = "update_machine"
FIELD_MANAGER_DIVISION_NAME = "Gerente de Campo"

CONFIRM_WORDS = {"confirmar", "confirma", "sim", "ok", "certo"}
CANCEL_WORDS = {"cancelar", "cancela", "nao", "não"}


def normalize_decimal(value):
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_text(text):
    return re.sub(r"\s+", " ", (text or "").strip())

def compact_machine_code(value):
    return re.sub(r"[\s._/-]+", "", (value or "").strip()).upper()

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


def get_manager_allowed_farm_ids(manager):
    return (
        manager.projeto
        .filter(ativo=True)
        .values_list("fazenda_id", flat=True)
        .distinct()
    )


def get_manager_allowed_machines(manager):
    farm_ids = get_manager_allowed_farm_ids(manager)

    return (
        Machine.objects
        .select_related("fazenda")
        .filter(
            is_active=True,
            fazenda_id__in=farm_ids,
        )
    )


def parse_machinery_message(text):
    raw = normalize_text(text)
    low = raw.lower()

    # HM TR23 1240
    m = re.search(
        r"^\s*HM\s+([a-zA-Z0-9._/-]+)\s+(\d+(?:[,.]\d+)?)\s*$",
        raw,
        re.I,
    )
    if m:
        return {
            "action": MachineWhatsappCommand.Action.UPDATE_HOURMETER,
            "machine_query": m.group(1).upper(),
            "hourmeter": normalize_decimal(m.group(2)),
            "plan_hours": None,
        }

    # Atualiza TR23 para 1240 / TR23 com 1240 horas
    m = re.search(
        r"\b([a-zA-Z0-9._/-]+)\b.*?\b(?:com|para|em|no)\s+(\d+(?:[,.]\d+)?)\s*h?(?:oras)?\b",
        raw,
        re.I,
    )
    if m and any(x in low for x in ["horimetro", "horímetro", "hora", "horas", "atualiza", "atualizar"]):
        return {
            "action": MachineWhatsappCommand.Action.UPDATE_HOURMETER,
            "machine_query": m.group(1).upper(),
            "hourmeter": normalize_decimal(m.group(2)),
            "plan_hours": None,
        }

    # REV TR23 300 1200
    m = re.search(
        r"^\s*REV\s+([a-zA-Z0-9._/-]+)\s+(\d+(?:[,.]\d+)?)\s+(\d+(?:[,.]\d+)?)\s*$",
        raw,
        re.I,
    )
    if m:
        return {
            "action": MachineWhatsappCommand.Action.REGISTER_REVISION,
            "machine_query": m.group(1).upper(),
            "plan_hours": normalize_decimal(m.group(2)),
            "hourmeter": normalize_decimal(m.group(3)),
        }

    # Revisão 300h TR23 com 1200 horas
    m = re.search(
        r"\b(?:rev|revisao|revisão)\s+(\d+(?:[,.]\d+)?)\s*h?.*?\b([a-zA-Z0-9._/-]+)\b.*?\b(?:com|no|em)\s+(\d+(?:[,.]\d+)?)",
        raw,
        re.I,
    )
    if m:
        return {
            "action": MachineWhatsappCommand.Action.REGISTER_REVISION,
            "machine_query": m.group(2).upper(),
            "plan_hours": normalize_decimal(m.group(1)),
            "hourmeter": normalize_decimal(m.group(3)),
        }

    return {
        "action": None,
        "machine_query": "",
        "hourmeter": None,
        "plan_hours": None,
    }


def parse_hourmeter_bulk_message(text):
    """
    Interpreta mensagens no padrão:

    HORIMETRO

    TR 23 - 1540
    TR 41 - 2201
    PV 08 - 873
    """

    raw_text = (text or "").strip()

    if not raw_text:
        return None

    lines = [
        (line or "").strip()
        for line in raw_text.splitlines()
        if (line or "").strip()
    ]

    if not lines:
        return None

    header = lines[0].strip().lower()

    if header not in {"horimetro", "horímetro"}:
        return None

    items = []
    invalid_lines = []
    empty_lines = []

    for line in lines[1:]:
        clean = line.strip()

        if not clean:
            continue

        m = re.match(
            r"^\s*(.+?)\s*[-–—:]\s*(\d+(?:[,.]\d+)?)?\s*$",
            clean,
            re.I,
        )

        if not m:
            invalid_lines.append(clean)
            continue

        machine_query = normalize_text(m.group(1)).upper()
        hourmeter_raw = (m.group(2) or "").strip()

        if not machine_query:
            invalid_lines.append(clean)
            continue

        if not hourmeter_raw:
            empty_lines.append(machine_query)
            continue

        hourmeter = normalize_decimal(hourmeter_raw)

        if hourmeter is None:
            invalid_lines.append(clean)
            continue

        items.append({
            "machine_query": machine_query,
            "hourmeter": hourmeter,
            "raw_line": clean,
        })

    return {
        "items": items,
        "invalid_lines": invalid_lines,
        "empty_lines": empty_lines,
    }
    


def find_machine_for_manager(manager, machine_query):
    query = (machine_query or "").strip()

    if not query:
        return None, []

    base_qs = get_manager_allowed_machines(manager)

    exact = list(base_qs.filter(identifier__iexact=query)[:5])

    if len(exact) == 1:
        return exact[0], exact

    if len(exact) > 1:
        return None, exact

    partial = list(
        base_qs
        .filter(identifier__icontains=query)
        .order_by("identifier")[:5]
    )

    if len(partial) == 1:
        return partial[0], partial

    query_compact = compact_machine_code(query)

    if query_compact:
        candidates = list(
            base_qs
            .order_by("identifier")[:500]
        )

        compact_matches = [
            machine
            for machine in candidates
            if compact_machine_code(machine.identifier) == query_compact
        ]

        if len(compact_matches) == 1:
            return compact_matches[0], compact_matches

        if len(compact_matches) > 1:
            return None, compact_matches[:5]

        compact_partial_matches = [
            machine
            for machine in candidates
            if query_compact in compact_machine_code(machine.identifier)
        ]

        if len(compact_partial_matches) == 1:
            return compact_partial_matches[0], compact_partial_matches

        if len(compact_partial_matches) > 1:
            return None, compact_partial_matches[:5]

    return None, partial



def get_pending_command(manager):
    return (
        MachineWhatsappCommand.objects
        .filter(
            manager=manager,
            status=MachineWhatsappCommand.Status.PENDING_CONFIRMATION,
        )
        .order_by("-created_at")
        .first()
    )


def extract_provider_message_id(resp):
    try:
        return ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        return ""


def log_outbound_template(manager, machine, template_name, body_text, resp, kind):
    provider_id = extract_provider_message_id(resp)

    OutboundMessage.objects.create(
        manager=manager,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=body_text,
        sent_at=timezone.now(),
        raw_response=resp,
        wa_status="sent" if provider_id else "",
        wa_sent_at=timezone.now() if provider_id else None,
    )


def send_command_confirmation(command):
    machine = command.machine
    payload = command.parsed_payload or {}

    if command.action == MachineWhatsappCommand.Action.UPDATE_HOURMETER:
        current_hourmeter = format_decimal_br(machine.current_hourmeter)
        new_hourmeter = format_decimal_br(payload.get("hourmeter"))

        resp = send_template(
            machine_command_phone(command),
            template_name="machine_update_confirmation",
            body_params=[
                f"{machine.identifier} - {machine.description}",
                str(machine.fazenda),
                "Horímetro",
                current_hourmeter,
                new_hourmeter,
            ],
        )

        body_text = (
            f"Confirmação horímetro | {machine.identifier} | "
            f"{current_hourmeter}h -> {new_hourmeter}h"
        )

        log_outbound_template(
            manager=command.manager,
            machine=machine,
            template_name="machine_update_confirmation",
            body_text=body_text,
            resp=resp,
            kind="machine_update_confirmation",
        )

        return resp

    if command.action == MachineWhatsappCommand.Action.REGISTER_REVISION:
        hourmeter = format_decimal_br(payload.get("hourmeter"))
        plan_label = payload.get("plan_name") or f"Revisão de {payload.get('plan_hours')}h"

        resp = send_template(
            machine_command_phone(command),
            template_name="machine_revision_confirmation",
            body_params=[
                f"{machine.identifier} - {machine.description}",
                str(machine.fazenda),
                plan_label,
                hourmeter,
            ],
        )

        body_text = (
            f"Confirmação revisão | {machine.identifier} | "
            f"{plan_label} | {hourmeter}h"
        )

        log_outbound_template(
            manager=command.manager,
            machine=machine,
            template_name="machine_revision_confirmation",
            body_text=body_text,
            resp=resp,
            kind="machine_revision_confirmation",
        )

        return resp

    return None


def machine_command_phone(command):
    return command.manager.phone_e164


def find_maintenance_plan(machine, plan_hours):
    if plan_hours is None:
        return None

    plans = (
        MaintenancePlan.objects
        .filter(
            farms=machine.fazenda,
            interval_hours=plan_hours,
            is_active=True,
        )
        .order_by("interval_hours", "name")
    )

    for plan in plans:
        if plan.applies_to_machine(machine):
            return plan

    return None


def get_field_managers_for_machine(machine, actor_manager):
    return (
        Manager.objects
        .filter(
            is_active=True,
            division__name__iexact=FIELD_MANAGER_DIVISION_NAME,
            projeto__fazenda_id=machine.fazenda_id,
        )
        .exclude(id=actor_manager.id if actor_manager else None)
        .distinct()
        .order_by("name")
    )


def notify_field_managers(command, action_label):
    machine = command.machine
    actor = command.manager

    managers = get_field_managers_for_machine(machine, actor)

    for manager in managers:
        try:
            resp = send_template(
                manager.phone_e164,
                template_name="machine_update_field_manager_notice",
                body_params=[
                    str(machine.fazenda),
                    f"{machine.identifier} - {machine.description}",
                    action_label,
                    actor.name if actor else "Sistema",
                ],
            )

            provider_id = extract_provider_message_id(resp)

            OutboundMessage.objects.create(
                manager=manager,
                to_phone=manager.phone_e164,
                provider_message_id=provider_id,
                kind="machine_update_field_manager_notice",
                text=(
                    f"Atualização maquinário | {machine.fazenda} | "
                    f"{machine.identifier} | {action_label} | "
                    f"Responsável: {actor.name if actor else 'Sistema'}"
                ),
                sent_at=timezone.now(),
                raw_response=resp,
                wa_status="sent" if provider_id else "",
                wa_sent_at=timezone.now() if provider_id else None,
            )
        except Exception:
            # Não quebra o salvamento principal se o aviso falhar.
            import logging
            logger = logging.getLogger("opscheckin.whatsapp")
            logger.exception(
                "MACHINE_FIELD_MANAGER_NOTICE_FAILED command_id=%s manager_id=%s",
                command.id,
                manager.id,
            )


@transaction.atomic
def apply_command(command):
    command = (
        MachineWhatsappCommand.objects
        .select_for_update()
        .select_related("machine", "manager")
        .get(id=command.id)
    )

    if command.status != MachineWhatsappCommand.Status.PENDING_CONFIRMATION:
        return False, "Esse comando não está mais pendente."

    machine = command.machine
    payload = command.parsed_payload or {}

    if not machine:
        command.status = MachineWhatsappCommand.Status.FAILED
        command.error_message = "Máquina não encontrada."
        command.save(update_fields=["status", "error_message"])
        return False, "Máquina não encontrada."

    hourmeter = normalize_decimal(payload.get("hourmeter"))

    if hourmeter is None:
        command.status = MachineWhatsappCommand.Status.FAILED
        command.error_message = "Horímetro inválido."
        command.save(update_fields=["status", "error_message"])
        return False, "Horímetro inválido."

    if hourmeter < 0:
        command.status = MachineWhatsappCommand.Status.FAILED
        command.error_message = "Horímetro negativo."
        command.save(update_fields=["status", "error_message"])
        return False, "Horímetro não pode ser negativo."

    if machine.current_hourmeter and hourmeter < machine.current_hourmeter:
        command.status = MachineWhatsappCommand.Status.FAILED
        command.error_message = "Horímetro menor que o atual."
        command.save(update_fields=["status", "error_message"])
        return (
            False,
            f"Não salvei. O horímetro atual é {format_decimal_br(machine.current_hourmeter)}h e você informou {format_decimal_br(hourmeter)}h.",
        )

    now = timezone.now()

    if command.action == MachineWhatsappCommand.Action.UPDATE_HOURMETER:
        reading = HourmeterReading.objects.create(
            machine=machine,
            value=hourmeter,
            measured_at=now,
            source=HourmeterReading.Source.WHATSAPP,
            notes=f"Atualizado via WhatsApp por {command.manager.name}",
            user_uid="",
            user_email="",
            user_display_name=command.manager.name,
        )

        command.status = MachineWhatsappCommand.Status.APPLIED
        command.confirmed_at = now
        command.applied_at = now
        command.applied_hourmeter_reading = reading
        command.save(
            update_fields=[
                "status",
                "confirmed_at",
                "applied_at",
                "applied_hourmeter_reading",
            ]
        )

        machine.refresh_from_db()

        action_label = f"Horímetro atualizado para {format_decimal_br(machine.current_hourmeter)}h"

        transaction.on_commit(
            lambda: notify_field_managers(command, action_label)
        )

        return (
            True,
            f"✅ Horímetro atualizado.\n\n{machine.identifier}: {format_decimal_br(machine.current_hourmeter)}h",
        )

    if command.action == MachineWhatsappCommand.Action.REGISTER_REVISION:
        plan_hours = normalize_decimal(payload.get("plan_hours"))
        plan = find_maintenance_plan(machine, plan_hours)

        if not plan:
            command.status = MachineWhatsappCommand.Status.FAILED
            command.error_message = "Plano de revisão não encontrado."
            command.save(update_fields=["status", "error_message"])
            return (
                False,
                "Não encontrei um plano de revisão ativo com essa quantidade de horas para essa fazenda/máquina.",
            )

        record = MaintenanceRecord.objects.create(
            machine=machine,
            maintenance_plan=plan,
            maintenance_type=MaintenanceRecord.MaintenanceType.REVISION,
            performed_at=now,
            hourmeter=hourmeter,
            description=plan.description,
            user_uid="",
            user_email="",
            user_display_name=command.manager.name,
        )

        command.status = MachineWhatsappCommand.Status.APPLIED
        command.confirmed_at = now
        command.applied_at = now
        command.applied_maintenance_record = record
        command.save(
            update_fields=[
                "status",
                "confirmed_at",
                "applied_at",
                "applied_maintenance_record",
            ]
        )

        machine.refresh_from_db()

        action_label = (
            f"{plan.name} registrada com {format_decimal_br(hourmeter)}h"
        )

        transaction.on_commit(
            lambda: notify_field_managers(command, action_label)
        )

        return (
            True,
            (
                f"✅ Revisão registrada.\n\n"
                f"{machine.identifier} - {plan.name}\n"
                f"Horímetro: {format_decimal_br(hourmeter)}h\n"
                f"Próxima revisão: {format_decimal_br(machine.next_revision_hourmeter)}h"
            ),
        )

    return False, "Tipo de comando não reconhecido."





def apply_bulk_hourmeter_update(*, manager, inbound, parsed_bulk):
    items = parsed_bulk.get("items") or []
    invalid_lines = parsed_bulk.get("invalid_lines") or []
    empty_lines = parsed_bulk.get("empty_lines") or []

    if not manager_can_update_machine(manager):
        send_text(
            manager.phone_e164,
            "Seu número está cadastrado, mas não está habilitado para atualizar máquinas pelo WhatsApp.",
        )
        return True

    if not items:
        message_lines = [
            "Não encontrei nenhum horímetro preenchido para salvar.",
            "",
            "Use o padrão:",
            "HORIMETRO",
            "",
            "TR 23 - 1540",
            "TR 41 - 2201",
        ]

        if empty_lines:
            message_lines.extend([
                "",
                f"Linhas sem valor: {len(empty_lines)}",
            ])

        if invalid_lines:
            message_lines.extend([
                "",
                "Linhas inválidas:",
                *invalid_lines[:10],
            ])

        send_text(manager.phone_e164, "\n".join(message_lines).strip())
        return True

    updated = []
    failed = []
    ambiguous = []

    for item in items:
        machine_query = item.get("machine_query")
        hourmeter = item.get("hourmeter")

        try:
            machine, matches = find_machine_for_manager(manager, machine_query)

            if not machine:
                if matches:
                    ambiguous.append(
                        f"{machine_query}: mais de uma máquina encontrada"
                    )
                else:
                    failed.append(
                        f"{machine_query}: máquina não encontrada nas fazendas liberadas"
                    )
                continue

            if hourmeter is None:
                failed.append(
                    f"{machine_query}: horímetro inválido"
                )
                continue

            if hourmeter < 0:
                failed.append(
                    f"{machine.identifier}: horímetro negativo"
                )
                continue

            if machine.current_hourmeter and hourmeter < machine.current_hourmeter:
                failed.append(
                    (
                        f"{machine.identifier}: informado {format_decimal_br(hourmeter)}h, "
                        f"atual {format_decimal_br(machine.current_hourmeter)}h"
                    )
                )
                continue

            with transaction.atomic():
                machine_locked = (
                    Machine.objects
                    .select_for_update()
                    .get(id=machine.id)
                )

                if machine_locked.current_hourmeter and hourmeter < machine_locked.current_hourmeter:
                    failed.append(
                        (
                            f"{machine_locked.identifier}: informado {format_decimal_br(hourmeter)}h, "
                            f"atual {format_decimal_br(machine_locked.current_hourmeter)}h"
                        )
                    )
                    continue

                now = timezone.now()

                reading = HourmeterReading.objects.create(
                    machine=machine_locked,
                    value=hourmeter,
                    measured_at=now,
                    source=HourmeterReading.Source.WHATSAPP,
                    notes=f"Atualizado via WhatsApp em lote por {manager.name}",
                    user_uid="",
                    user_email="",
                    user_display_name=manager.name,
                )

                command = MachineWhatsappCommand.objects.create(
                    manager=manager,
                    inbound_message=inbound,
                    machine=machine_locked,
                    action=MachineWhatsappCommand.Action.UPDATE_HOURMETER,
                    status=MachineWhatsappCommand.Status.APPLIED,
                    original_text=item.get("raw_line") or "",
                    parsed_payload={
                        "machine_query": machine_query,
                        "hourmeter": str(hourmeter),
                        "plan_hours": None,
                        "plan_name": "",
                        "bulk": True,
                    },
                    confirmed_at=now,
                    applied_at=now,
                    applied_hourmeter_reading=reading,
                )

                updated.append(
                    f"✅ {machine_locked.identifier}: {format_decimal_br(hourmeter)}h"
                )

                action_label = f"Horímetro atualizado para {format_decimal_br(hourmeter)}h"

                transaction.on_commit(
                    lambda command_id=command.id, action_label=action_label: notify_field_managers(
                        MachineWhatsappCommand.objects
                        .select_related("machine", "manager")
                        .get(id=command_id),
                        action_label,
                    )
                )

        except Exception:
            logger.exception(
                "MACHINE_BULK_HOURMETER_ITEM_FAILED manager_id=%s machine_query=%s inbound_id=%s",
                getattr(manager, "id", None),
                machine_query,
                getattr(inbound, "id", None),
            )
            failed.append(
                f"{machine_query}: erro interno ao processar"
            )

    response_lines = []

    if updated:
        response_lines.append(f"Horímetros atualizados: {len(updated)}")
        response_lines.extend(updated)

    if failed:
        response_lines.append("")
        response_lines.append(f"Não salvos: {len(failed)}")
        response_lines.extend([f"⚠️ {line}" for line in failed[:15]])

    if ambiguous:
        response_lines.append("")
        response_lines.append(f"Ambíguos: {len(ambiguous)}")
        response_lines.extend([f"⚠️ {line}" for line in ambiguous[:15]])

    if invalid_lines:
        response_lines.append("")
        response_lines.append(f"Linhas inválidas: {len(invalid_lines)}")
        response_lines.extend([f"⚠️ {line}" for line in invalid_lines[:10]])

    if empty_lines:
        response_lines.append("")
        response_lines.append(f"Linhas ignoradas sem horímetro: {len(empty_lines)}")

    if not response_lines:
        response_lines.append("Nenhum horímetro foi atualizado.")

    send_text(manager.phone_e164, "\n".join(response_lines).strip())

    return True

def handle_machinery_whatsapp_message(*, manager, inbound, text):
    raw = normalize_text(text)
    low = raw.lower()

    parsed_bulk = parse_hourmeter_bulk_message(text)

    if parsed_bulk is not None:
        return apply_bulk_hourmeter_update(
            manager=manager,
            inbound=inbound,
            parsed_bulk=parsed_bulk,
        )

    pending = get_pending_command(manager)

    if pending and low in CONFIRM_WORDS:
        ok, message = apply_command(pending)
        send_text(manager.phone_e164, message)
        return True

    if pending and low in CANCEL_WORDS:
        pending.status = MachineWhatsappCommand.Status.CANCELLED
        pending.save(update_fields=["status"])
        send_text(manager.phone_e164, "Operação cancelada. Nada foi salvo.")
        return True

    parsed = parse_machinery_message(raw)

    if not parsed.get("action"):
        return False

    if not manager_can_update_machine(manager):
        send_text(
            manager.phone_e164,
            "Seu número está cadastrado, mas não está habilitado para atualizar máquinas pelo WhatsApp.",
        )
        return True

    if parsed.get("hourmeter") is None:
        send_text(
            manager.phone_e164,
            "Não consegui identificar o horímetro. Use: HM TR23 1240 ou REV TR23 300 1200",
        )
        return True

    machine, matches = find_machine_for_manager(manager, parsed.get("machine_query"))

    if not machine:
        if matches:
            lines = [
                f"{idx}) {item.identifier} - {item.description} - {item.fazenda}"
                for idx, item in enumerate(matches, start=1)
            ]
            send_text(
                manager.phone_e164,
                "Encontrei mais de uma máquina parecida. Envie o identificador mais específico:\n\n"
                + "\n".join(lines),
            )
            return True

        send_text(
            manager.phone_e164,
            "Não encontrei essa máquina entre as fazendas liberadas para seu número.",
        )
        return True

    hourmeter = parsed["hourmeter"]

    if machine.current_hourmeter and hourmeter < machine.current_hourmeter:
        send_text(
            manager.phone_e164,
            (
                "Não salvei.\n\n"
                f"A máquina {machine.identifier} está com {format_decimal_br(machine.current_hourmeter)}h.\n"
                f"Você informou {format_decimal_br(hourmeter)}h, que é menor que o atual."
            ),
        )
        return True

    plan_name = ""
    if parsed["action"] == MachineWhatsappCommand.Action.REGISTER_REVISION:
        plan = find_maintenance_plan(machine, parsed.get("plan_hours"))
        if not plan:
            send_text(
                manager.phone_e164,
                "Não encontrei um plano de revisão ativo com essa quantidade de horas para essa fazenda/máquina.",
            )
            return True

        plan_name = plan.name

    command = MachineWhatsappCommand.objects.create(
        manager=manager,
        inbound_message=inbound,
        machine=machine,
        action=parsed["action"],
        status=MachineWhatsappCommand.Status.PENDING_CONFIRMATION,
        original_text=raw,
        parsed_payload={
            "machine_query": parsed.get("machine_query"),
            "hourmeter": str(parsed.get("hourmeter")),
            "plan_hours": str(parsed.get("plan_hours")) if parsed.get("plan_hours") is not None else None,
            "plan_name": plan_name,
        },
    )

    try:
        send_command_confirmation(command)
    except Exception:
        # fallback se template ainda não estiver aprovado/liberado
        if command.action == MachineWhatsappCommand.Action.UPDATE_HOURMETER:
            send_text(
                manager.phone_e164,
                (
                    "Confirme a atualização do horímetro:\n\n"
                    f"Máquina: {machine.identifier} - {machine.description}\n"
                    f"Fazenda: {machine.fazenda}\n"
                    f"Horímetro atual: {format_decimal_br(machine.current_hourmeter)}h\n"
                    f"Novo horímetro: {format_decimal_br(hourmeter)}h\n\n"
                    "Responda CONFIRMAR para salvar ou CANCELAR para ignorar."
                ),
            )
        else:
            send_text(
                manager.phone_e164,
                (
                    "Confirme o registro da revisão:\n\n"
                    f"Máquina: {machine.identifier} - {machine.description}\n"
                    f"Fazenda: {machine.fazenda}\n"
                    f"Revisão: {plan_name}\n"
                    f"Horímetro informado: {format_decimal_br(hourmeter)}h\n\n"
                    "Responda CONFIRMAR para salvar ou CANCELAR para ignorar."
                ),
            )

    return True