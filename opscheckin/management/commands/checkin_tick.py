# opscheckin/management/commands/checkin_tick.py
from __future__ import annotations

from datetime import datetime
import logging

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from opscheckin.models import Manager, DailyCheckin, OutboundQuestion, OutboundMessage
from opscheckin.services.whatsapp import send_text, send_template

logger = logging.getLogger("opscheckin.checkin_tick")

DEFAULT_AGENDA_TEMPLATE = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)

DEFAULT_REMINDER_TEXT = "??"

# JANELA OFICIAL
# AGENDA_HOUR = 6
# AGENDA_MINUTE = 0
AGENDA_HOUR = 8
AGENDA_MINUTE = 30

# Reminders “cravados” (modelo A)
# (hour, minute, expected_reminder_count)
# REMINDER_SLOTS = [
#     (6, 15, 0),
#     (6, 30, 1),
#     (6, 45, 2),
#     (7, 0, 3),
# ]


REMINDER_SLOTS = [
    (8, 45, 0),  # +15 min
    (9, 0, 1),   # +30 min
    (9, 15, 2),  # +45 min
    (9, 30, 3),  # +60 min
]

MIN_CHARS_DEFAULT = 15
MARK_MISSED_AFTER_MIN_DEFAULT = 120
SLOT_GRACE_SECONDS_DEFAULT = 120  # 2 min

# Janela de sessão do WhatsApp (24h desde a última msg do cliente)
REENGAGEMENT_HOURS = 24


def _local_today():
    return timezone.localdate()


def _ensure_checkin(manager: Manager, day):
    checkin, _ = DailyCheckin.objects.get_or_create(manager=manager, date=day)
    return checkin


def _log_outbound(
    *,
    manager: Manager,
    checkin: DailyCheckin,
    related_question: OutboundQuestion | None,
    kind: str,
    text: str,
    now,
    resp: dict | None,
):
    provider_id = ""
    try:
        provider_id = ((resp or {}).get("messages") or [{}])[0].get("id") or ""
    except Exception:
        provider_id = ""

    OutboundMessage.objects.create(
        manager=manager,
        checkin=checkin,
        related_question=related_question,
        to_phone=manager.phone_e164,
        provider_message_id=provider_id,
        kind=kind,
        text=text,
        sent_at=now,
        raw_response=resp,
    )


def _mark_missed_if_needed(q: OutboundQuestion, *, now, mark_missed_after_min: int):
    if q.status != "pending":
        return
    if not q.sent_at:
        return
    if q.answered_at:
        return

    age_min = (now - q.sent_at).total_seconds() / 60.0
    if age_min >= mark_missed_after_min:
        q.status = "missed"
        q.save(update_fields=["status"])


def _needs_followup(q: OutboundQuestion, *, min_chars: int) -> bool:
    if q.status != "pending":
        return False
    if not q.sent_at:
        return False
    if q.answered_at:
        return False

    txt = (q.answer_text or "").strip()
    if not txt:
        return True
    return len(txt) < min_chars


def _slot_window(local_now, hour: int, minute: int, grace_seconds: int):
    start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timezone.timedelta(seconds=grace_seconds)
    return start, end


def _is_in_slot(local_now, hour: int, minute: int, grace_seconds: int) -> bool:
    start, end = _slot_window(local_now, hour, minute, grace_seconds)
    return start <= local_now < end


def _already_sent_in_this_slot(q: OutboundQuestion, *, local_now, hour: int, minute: int, grace_seconds: int) -> bool:
    anchor = q.last_reminder_at or q.sent_at
    if not anchor:
        return False

    anchor_local = timezone.localtime(anchor)
    start, end = _slot_window(local_now, hour, minute, grace_seconds)
    return start <= anchor_local < end


# -------- WhatsApp session / inbound detection --------

def _get_inbound_model():
    """
    Tenta localizar um model de inbound sem acoplar hard.
    Ajuste aqui se o nome do seu model for diferente.
    """
    for model_name in ("InboundMessage", "InboundWhatsAppMessage", "WhatsAppInboundMessage"):
        try:
            return apps.get_model("opscheckin", model_name)
        except Exception:
            continue
    return None


def _last_inbound_at(manager: Manager):
    """
    Pega a data/hora da última mensagem inbound do manager.
    Tenta campos comuns: received_at, created_at, timestamp.
    """
    M = _get_inbound_model()
    if not M:
        return None

    qs = M.objects.all()
    # tenta relacionamentos comuns
    if hasattr(M, "manager_id"):
        qs = qs.filter(manager=manager)
    elif hasattr(M, "from_phone"):
        qs = qs.filter(from_phone=manager.phone_e164)
    elif hasattr(M, "wa_id"):
        qs = qs.filter(wa_id=manager.phone_e164)

    # tenta ordenar por campos comuns
    for field in ("received_at", "created_at", "timestamp", "ts"):
        if hasattr(M, field):
            last = qs.order_by(f"-{field}").first()
            if last:
                return getattr(last, field, None)
    return None


def _can_send_freeform(now, last_inbound_at) -> bool:
    if not last_inbound_at:
        return False
    delta = now - last_inbound_at
    return delta.total_seconds() <= (REENGAGEMENT_HOURS * 3600)


def _wa_error_code_from_exception(exc) -> int | None:
    """
    Tenta extrair código de erro WhatsApp/Graph (ex: 131047) de um HTTPError.
    """
    resp = getattr(exc, "response", None)
    if not resp:
        return None
    try:
        data = resp.json()
    except Exception:
        return None

    # formatos comuns do Graph
    # {"error":{"message":"...","type":"OAuthException","code":131047,"error_data":{"details":"..."}}}
    try:
        return int(data.get("error", {}).get("code"))
    except Exception:
        return None


def _get_template_names():
    """
    Settings:
      WHATSAPP_TEMPLATE_AGENDA_NAME
      WHATSAPP_TEMPLATE_REMINDER_NAME
      WHATSAPP_TEMPLATE_LANGUAGE  (default pt_BR)
    """
    agenda_name = (getattr(settings, "WHATSAPP_TEMPLATE_AGENDA_NAME", "") or "").strip()
    reminder_name = (getattr(settings, "WHATSAPP_TEMPLATE_REMINDER_NAME", "") or "").strip()
    language = (getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR") or "pt_BR").strip()
    return agenda_name, reminder_name, language


def _send_with_fallback(
    *,
    manager: Manager,
    kind: str,
    text_body: str,
    template_name: str,
    template_params,
):
    """
    Estratégia:
      1) tenta text (freeform)
      2) se cair 131047, tenta template (se configurado)
      3) se não tiver template, só loga e retorna None (sem exception)
    """
    now = timezone.now()
    last_in = _last_inbound_at(manager)
    agenda_name, reminder_name, lang = _get_template_names()

    # seleciona template conforme kind, mas permite sobrescrever pelo argumento template_name
    chosen_template = (template_name or "").strip()
    if not chosen_template:
        chosen_template = agenda_name if kind == "agenda" else reminder_name

    # se estiver dentro da janela 24h, manda texto direto
    if _can_send_freeform(now, last_in):
        try:
            return send_text(manager.phone_e164, text_body)
        except Exception as e:
            # mesmo dentro de 24h, não queremos quebrar o tick
            logger.exception("WAPP_SEND_TEXT_FAIL kind=%s to=%s err=%s", kind, manager.phone_e164, str(e))
            return None

    # fora da janela: tentar template
    if not chosen_template:
        logger.warning(
            "WAPP_OUT_OF_WINDOW_NO_TEMPLATE kind=%s manager=%s to=%s (configure WHATSAPP_TEMPLATE_*_NAME)",
            kind, manager.name, manager.phone_e164,
        )
        return None

    try:
        return send_template(
            manager.phone_e164,
            template_name=chosen_template,
            language_code=lang,
            body_params=template_params,
        )
    except Exception as e:
        logger.exception(
            "WAPP_SEND_TEMPLATE_FAIL kind=%s tpl=%s to=%s err=%s",
            kind, chosen_template, manager.phone_e164, str(e)
        )
        return None


# -------- Business flow --------

def _send_agenda_if_needed(*, manager: Manager, checkin: DailyCheckin, now, agenda_text: str):
    """
    Garante que existe UMA pergunta AGENDA enviada no dia.
    Só cria/envia se ainda não tiver AGENDA com sent_at.
    """
    q = (
        checkin.questions
        .filter(step="AGENDA")
        .order_by("-scheduled_for", "-id")
        .first()
    )
    if q and q.sent_at:
        return q

    final_msg = agenda_text.format(name=manager.name)

    # cria a pergunta, mas só marca sent_at após envio OK
    q = OutboundQuestion.objects.create(
        checkin=checkin,
        step="AGENDA",
        scheduled_for=now,
        status="pending",
        prompt_text=final_msg,
    )

    # TEMPLATE params: você decide o formato no template
    # Sugestão: BODY: "Bom dia {{1}}!\n\n{{2}}"
    resp = _send_with_fallback(
        manager=manager,
        kind="agenda",
        text_body=final_msg,
        template_name="",
        template_params={  # <- dict nomeado
            "manager_name": manager.name,
            "agenda_text": "Por favor, poderia me mandar a sua agenda do dia?",
        },
    )

    if resp:
        q.sent_at = now
        q.save(update_fields=["sent_at"])

        _log_outbound(
            manager=manager,
            checkin=checkin,
            related_question=q,
            kind="agenda",
            text=final_msg,
            now=now,
            resp=resp,
        )
    else:
        # não marca sent_at; fica pendente pra tentar novamente
        logger.warning("AGENDA_NOT_SENT manager=%s to=%s", manager.name, manager.phone_e164)

    return q


def _send_reminder(q: OutboundQuestion, *, now, reminder_text: str):
    manager = q.checkin.manager
    if not manager:
        return

    resp = _send_with_fallback(
        manager=manager,
        kind="reminder",
        text_body=reminder_text,
        template_name="",
        template_params={
            "manager_name": manager.name,
            "reminder_text": reminder_text,
        },
    )

    if not resp:
        logger.warning("REMINDER_NOT_SENT manager=%s to=%s", manager.name, manager.phone_e164)
        return

    _log_outbound(
        manager=manager,
        checkin=q.checkin,
        related_question=q,
        kind="reminder",
        text=reminder_text,
        now=now,
        resp=resp,
    )

    q.reminder_count += 1
    q.last_reminder_at = now
    q.save(update_fields=["reminder_count", "last_reminder_at"])


class Command(BaseCommand):
    help = "Dispara AGENDA e faz reminders/missed (modelo A: horários cravados)."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="YYYY-MM-DD (padrão: hoje local)")
        parser.add_argument("--include-inactive", action="store_true", help="Inclui managers inativos (padrão: False)")
        parser.add_argument("--send-agenda-now", action="store_true", help="Força criar/enviar AGENDA agora (se não enviada ainda)")
        parser.add_argument("--agenda-text", type=str, default=DEFAULT_AGENDA_TEMPLATE, help="Template da AGENDA (usa {name})")

        parser.add_argument("--min-chars", type=int, default=MIN_CHARS_DEFAULT, help="Se resposta < min-chars, continua cobrando")
        parser.add_argument("--max-reminders", type=int, default=4, help="Máximo reminders (default: 4)")
        parser.add_argument("--mark-missed-after-min", type=int, default=MARK_MISSED_AFTER_MIN_DEFAULT, help="Marca missed após X min pendente")
        parser.add_argument("--reminder-text", type=str, default=DEFAULT_REMINDER_TEXT, help="Texto do reminder (ex: ??)")
        parser.add_argument("--slot-grace-seconds", type=int, default=SLOT_GRACE_SECONDS_DEFAULT, help="Janela de tolerância do slot")

    def handle(self, *args, **opts):
        now = timezone.now()
        local_now = timezone.localtime(now)

        day = _local_today()
        if opts["date"]:
            try:
                day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            except Exception:
                self.stdout.write(self.style.WARNING("date inválida; usando hoje"))

        include_inactive = bool(opts["include_inactive"])
        send_agenda_now = bool(opts["send_agenda_now"])
        agenda_text = (opts["agenda_text"] or DEFAULT_AGENDA_TEMPLATE).strip()
        reminder_text = (opts["reminder_text"] or DEFAULT_REMINDER_TEXT).strip() or "??"

        min_chars = int(opts["min_chars"] or MIN_CHARS_DEFAULT)
        max_reminders = int(opts["max_reminders"] or 4)
        mark_missed_after_min = int(opts["mark_missed_after_min"] or MARK_MISSED_AFTER_MIN_DEFAULT)
        grace_seconds = int(opts["slot_grace_seconds"] or SLOT_GRACE_SECONDS_DEFAULT)

        managers_qs = (
            Manager.objects.all().order_by("name")
            if include_inactive
            else Manager.objects.filter(is_active=True).order_by("name")
        )

        self.stdout.write(
            f"[checkin_tick] day={day} now={now.isoformat()} local_now={local_now.isoformat()} "
            f"managers={managers_qs.count()} include_inactive={include_inactive}"
        )

        # Descobre se AGORA é um slot de reminder e qual expected_count
        current_slot = None
        for (hh, mm, expected_count) in REMINDER_SLOTS:
            if _is_in_slot(local_now, hh, mm, grace_seconds):
                current_slot = (hh, mm, expected_count)
                break

        for m in managers_qs:
            checkin = _ensure_checkin(m, day)

            # 1) AGENDA às 06:00 (ou forçado)
            agenda_q = (
                checkin.questions
                .filter(step="AGENDA")
                .order_by("-scheduled_for", "-id")
                .first()
            )

            if send_agenda_now:
                agenda_q = _send_agenda_if_needed(manager=m, checkin=checkin, now=now, agenda_text=agenda_text)
            else:
                if _is_in_slot(local_now, AGENDA_HOUR, AGENDA_MINUTE, grace_seconds):
                    agenda_q = _send_agenda_if_needed(manager=m, checkin=checkin, now=now, agenda_text=agenda_text)

            if not agenda_q:
                continue

            # 2) missed
            _mark_missed_if_needed(agenda_q, now=now, mark_missed_after_min=mark_missed_after_min)

            # 3) reminders cravados por reminder_count
            if not current_slot:
                continue

            hh, mm, expected_count = current_slot

            if agenda_q.reminder_count >= max_reminders:
                continue

            if agenda_q.reminder_count != expected_count:
                continue

            if _already_sent_in_this_slot(agenda_q, local_now=local_now, hour=hh, minute=mm, grace_seconds=grace_seconds):
                continue

            if not _needs_followup(agenda_q, min_chars=min_chars):
                continue

            _send_reminder(agenda_q, now=now, reminder_text=reminder_text)
            self.stdout.write(f"  - reminder attempted slot={hh:02d}:{mm:02d} to {m.name} count={agenda_q.reminder_count}")

        self.stdout.write(self.style.SUCCESS("[checkin_tick] done"))