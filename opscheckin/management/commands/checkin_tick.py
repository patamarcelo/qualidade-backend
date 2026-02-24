from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from django.db import transaction

from opscheckin.models import Manager, DailyCheckin, OutboundQuestion
from opscheckin.flow import SLOTS
from opscheckin.whatsapp import send_whatsapp_text

REMINDER_AFTER_MIN = 30   # 1ª cobrança após 30 min
MARK_MISSED_AFTER_MIN = 120  # se ficar 2h pendente, marca como missed (não trava o dia)

def _local_today():
    # timezone do Django deve estar configurada p/ America/Sao_Paulo
    return timezone.localdate()

def _slot_dt(today, slot_time):
    # cria datetime local para o slot
    return timezone.make_aware(datetime.combine(today, slot_time))

class Command(BaseCommand):
    help = "Dispara perguntas do check-in e faz cobranças."

    def handle(self, *args, **options):
        now = timezone.now()
        today = _local_today()

        managers = Manager.objects.filter(is_active=True)

        for m in managers:
            checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=today)

            # 1) garante que os objetos de slot existam (um por step)
            for step, t, _text in SLOTS:
                scheduled_for = _slot_dt(today, t)
                OutboundQuestion.objects.get_or_create(
                    checkin=checkin,
                    step=step,
                    defaults={"scheduled_for": scheduled_for},
                )

            # 2) envia perguntas cujo scheduled_for já passou e ainda não foram enviadas
            due = (checkin.questions
                   .filter(sent_at__isnull=True, scheduled_for__lte=now)
                   .order_by("scheduled_for"))

            for q in due:
                text = dict((s, msg) for s, _t, msg in SLOTS)[q.step]
                send_whatsapp_text(m.phone_e164, text)
                q.sent_at = now
                q.status = "pending"
                q.save(update_fields=["sent_at", "status"])

            # 3) cobranças (1 vez) para pendências
            pending = (checkin.questions
                       .filter(status="pending", sent_at__isnull=False, answered_at__isnull=True)
                       .order_by("scheduled_for"))

            for q in pending:
                age_min = (now - q.sent_at).total_seconds() / 60.0

                # marca missed depois de um tempo (não deixa travar o fluxo)
                if age_min >= MARK_MISSED_AFTER_MIN:
                    q.status = "missed"
                    q.save(update_fields=["status"])
                    continue

                # 1 cobrança
                if age_min >= REMINDER_AFTER_MIN and q.reminder_count == 0:
                    reminder = (
                        "Só confirmando 🙂\n"
                        "Ainda não recebi sua resposta da última pergunta.\n"
                        "Quando puder, responde aqui mesmo."
                    )
                    send_whatsapp_text(m.phone_e164, reminder)
                    q.reminder_count = 1
                    q.last_reminder_at = now
                    q.save(update_fields=["reminder_count", "last_reminder_at"])