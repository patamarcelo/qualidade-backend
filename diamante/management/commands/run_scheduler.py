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

        result = start()

        if not result or not result.get("ok"):
            reason = (result or {}).get("reason")
            error = (result or {}).get("error")

            if reason == "lock_active":
                self.stdout.write(
                    self.style.WARNING("Scheduler não iniciado: advisory lock já está ativo em outro processo.")
                )
            elif reason == "lock_error":
                self.stdout.write(
                    self.style.ERROR(f"Scheduler falhou ao adquirir advisory lock: {error}")
                )
            elif reason == "startup_error":
                self.stdout.write(
                    self.style.ERROR(f"Scheduler falhou ao iniciar: {error}")
                )
            elif reason == "debug_mode":
                self.stdout.write(
                    self.style.WARNING("Scheduler não iniciado porque DEBUG=True.")
                )
            else:
                self.stdout.write(
                    self.style.ERROR("Scheduler não iniciado por motivo desconhecido.")
                )
            return

        scheduler = result["scheduler"]
        self.stdout.write(self.style.SUCCESS("Scheduler iniciado com sucesso."))

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