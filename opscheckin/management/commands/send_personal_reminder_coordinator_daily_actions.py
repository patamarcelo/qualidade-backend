from django.core.management.base import BaseCommand
from django.utils import timezone

from opscheckin.services.personal_reminder_coordinators import (
    get_active_personal_reminder_coordinators,
    send_coordinator_daily_action_template,
)


class Command(BaseCommand):
    help = "Envia aos coordenadores o botão para receber o resumo diário dos avisos pessoais."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Força o envio mesmo se já tiver sido enviado hoje ou se não houver atividade.",
        )

    def handle(self, *args, **options):
        day = timezone.localdate()
        force = bool(options.get("force"))

        coordinators = list(get_active_personal_reminder_coordinators())

        sent = 0
        skipped = 0

        for coordinator in coordinators:
            ok = send_coordinator_daily_action_template(
                coordinator=coordinator,
                day=day,
                force=force,
            )

            if ok:
                sent += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                "[personal_reminder_coordinator_daily_actions] "
                f"coordinators={len(coordinators)} sent={sent} skipped={skipped} "
                f"force={force} day={day}"
            )
        )