from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.models import Manager
from opscheckin.services.checkin import ensure_slots_for_today, send_due_questions
from opscheckin.services.reminders import process_pending


class Command(BaseCommand):
    help = "Dispara perguntas do check-in (slots), envia as que estão vencidas e faz cobranças."

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()

        managers = Manager.objects.filter(is_active=True)

        for m in managers:
            checkin = ensure_slots_for_today(m, today=today)
            send_due_questions(checkin, now=now)

        # cobranças / missed (global)
        process_pending(now=now)