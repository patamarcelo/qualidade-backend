from datetime import datetime, time
from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import Manager, DailyCheckin, OutboundQuestion
from opscheckin.services.whatsapp import send_text
from opscheckin.services.reminders import process_agenda_reminders

from opscheckin.services.templates import render_message

AGENDA_SEND_TIME = time(6, 0)
AGENDA_TEXT = (
    "Bom dia {name},\n\n"
    "Por favor poderia me mandar a sua agenda do dia?"
)

def _slot_dt(today, slot_time):
    return timezone.make_aware(datetime.combine(today, slot_time))

class Command(BaseCommand):
    help = "Dispara AGENDA 06:00 e processa cobranças do AGENDA."

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()

        managers = Manager.objects.filter(is_active=True)

        for m in managers:
            checkin, _ = DailyCheckin.objects.get_or_create(manager=m, date=today)

            scheduled_for = _slot_dt(today, AGENDA_SEND_TIME)

            q, created = OutboundQuestion.objects.get_or_create(
                checkin=checkin,
                step="AGENDA",
                defaults={"scheduled_for": scheduled_for, "status": "pending"},
            )

            # envia somente se:
            # - já passou 06:00
            # - ainda não foi enviado
            # - não existe outra pergunta enviada pendente (pra não misturar)
            if now >= scheduled_for and q.sent_at is None:
                has_open = checkin.questions.filter(
                    status="pending",
                    sent_at__isnull=False,
                    answered_at__isnull=True,
                ).exclude(id=q.id).exists()

                if not has_open:
                    msg = render_message(AGENDA_TEXT, m)
                    send_text(m.phone_e164, msg)
                    q.sent_at = now
                    q.status = "pending"
                    q.save(update_fields=["sent_at", "status"])

        # cobranças do AGENDA
        process_agenda_reminders(now=now)