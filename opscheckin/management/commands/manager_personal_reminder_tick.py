from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.services.personal_reminders import run_personal_reminder_tick


class Command(BaseCommand):
    help = "Processa lembretes pessoais dos managers"

    def handle(self, *args, **options):
        result = run_personal_reminder_tick(now_local=timezone.localtime(timezone.now()))
        self.stdout.write(
            self.style.SUCCESS(
                "[manager_personal_reminder_tick] "
                f"reminders={result['reminders']} "
                f"eligible={result['eligible']} "
                f"sent={result['sent']} "
                f"existing={result['existing']} "
                f"failed={result['failed']} "
                f"expired={result['expired']}"
            )
        )