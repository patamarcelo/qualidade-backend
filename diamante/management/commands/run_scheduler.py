import time
import logging

from django.core.management.base import BaseCommand
from django.db import connection

from diamante.scheduler import start

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Inicia o APScheduler em processo dedicado"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Iniciando scheduler..."))

        scheduler = start()

        try:
            while True:
                connection.close_if_unusable_or_obsolete()
                time.sleep(30)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Encerrando scheduler..."))
            try:
                scheduler.shutdown()
            except Exception:
                logger.exception("Erro ao encerrar scheduler")