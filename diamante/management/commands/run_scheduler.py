import time
import logging
from django.core.management.base import BaseCommand
from django.db import connection, close_old_connections
from diamante.scheduler import start

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Inicia o APScheduler em processo dedicado (Resiliente)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Iniciando container do scheduler..."))

        result = start()

        if not result or not result.get("ok"):
            reason = (result or {}).get("reason", "unknown")
            error = (result or {}).get("error", "")
            
            if reason == "lock_active":
                self.stdout.write(self.style.WARNING("Scheduler já em execução em outro processo."))
            else:
                self.stdout.write(self.style.ERROR(f"Erro crítico: {reason} | {error}"))
            return

        scheduler = result["scheduler"]
        self.stdout.write(self.style.SUCCESS("Scheduler ativo e monitorando jobs."))

        try:
            loop_count = 0
            while True:
                # Limpa conexões inativas para evitar que o processo pai morra por timeout de rede
                close_old_connections()
                connection.close_if_unusable_or_obsolete()
                
                loop_count += 1
                if loop_count >= 30:  # Loga healthcheck a cada 15 min (30 * 30s)
                    logger.info("Scheduler Process Healthcheck: Running OK.")
                    loop_count = 0
                
                time.sleep(30)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Encerrando via interrupção do usuário..."))
        except Exception as e:
            logger.error(f"Erro no loop principal do comando: {e}")
        finally:
            if scheduler.running:
                scheduler.shutdown()
                self.stdout.write(self.style.SUCCESS("Scheduler encerrado com segurança."))