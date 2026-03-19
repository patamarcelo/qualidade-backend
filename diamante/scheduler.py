import logging
import pytz
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from django_apscheduler.jobstores import register_events
from django_apscheduler.models import DjangoJobExecution

from django.conf import settings
from django.db import close_old_connections, connection

# Imports das suas funções de negócio
from diamante.utils import (
    finalizar_parcelas_encerradas,
    enviar_email_alerta_mungo_verde_por_regra,
)
from diamante.cron import (
    enviar_email_estoque_farmbox_diario,
    enviar_email_diario,
    update_farmbox_mongodb_app,
)
from opscheckin.cron import (
    run_opscheckin_agenda_0600,
    run_opscheckin_reminders,
    run_opscheckin_agenda_followups,
    run_opscheckin_agenda_confirm,
    run_opscheckin_director_agenda_summary,
    run_opscheckin_daily_manager_event_tick,
)

from .scheduler_lock import acquire_scheduler_lock

logger = logging.getLogger(__name__)

def _prepare_db_for_job():
    """Garante que a conexão com o banco esteja fresca antes de rodar o job."""
    close_old_connections()
    connection.close_if_unusable_or_obsolete()

def delete_old_job_executions(max_age=604_800):
    """Apaga logs antigos de execuções do APScheduler (default: 7 dias)."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)

# =====================================================================
# JOB WRAPPERS SERIALIZÁVEIS (Garantem estabilidade de conexão)
# =====================================================================

def job_finalizar_parcelas_encerradas():
    _prepare_db_for_job()
    return finalizar_parcelas_encerradas()

def job_update_farmbox_mongodb_app():
    _prepare_db_for_job()
    return update_farmbox_mongodb_app()

def job_enviar_email_diario():
    _prepare_db_for_job()
    return enviar_email_diario()

def job_enviar_email_alerta_mungo_verde_por_regra():
    _prepare_db_for_job()
    return enviar_email_alerta_mungo_verde_por_regra()

def job_enviar_email_estoque_farmbox_diario():
    _prepare_db_for_job()
    return enviar_email_estoque_farmbox_diario()

def job_run_opscheckin_agenda_0600():
    _prepare_db_for_job()
    return run_opscheckin_agenda_0600()

def job_run_opscheckin_reminders():
    _prepare_db_for_job()
    return run_opscheckin_reminders()

def job_run_opscheckin_agenda_followups():
    _prepare_db_for_job()
    return run_opscheckin_agenda_followups()

def job_run_opscheckin_agenda_confirm():
    _prepare_db_for_job()
    return run_opscheckin_agenda_confirm()

def job_run_opscheckin_director_agenda_summary():
    _prepare_db_for_job()
    return run_opscheckin_director_agenda_summary()

def job_run_opscheckin_daily_manager_event_tick():
    _prepare_db_for_job()
    return run_opscheckin_daily_manager_event_tick()

def job_delete_old_job_executions():
    _prepare_db_for_job()
    return delete_old_job_executions()

# =====================================================================
# INICIALIZAÇÃO DO SCHEDULER
# =====================================================================

def start():
    _prepare_db_for_job()

    try:
        has_lock = acquire_scheduler_lock(lock_id=777002)
    except Exception as e:
        logger.error("Erro ao adquirir advisory lock do scheduler: %s", e, exc_info=True)
        return {"ok": False, "reason": "lock_error", "error": str(e)}

    if not has_lock:
        return {"ok": False, "reason": "lock_active"}

    try:
        fuso_horario = pytz.timezone(settings.TIME_ZONE)
        
        # Uso do MemoryJobStore para isolar a agenda das falhas de SSL do Postgres
        scheduler = BackgroundScheduler(
            timezone=fuso_horario,
            jobstores={'default': MemoryJobStore()}
        )

        if settings.DEBUG is False:
            logger.info("Agendando jobs (Store: MEMORY) | Timezone: %s", settings.TIME_ZONE)

            # GRUPO A — FINANCEIRO
            scheduler.add_job(
                job_finalizar_parcelas_encerradas, "cron", day_of_week="*", hour="5", minute="30",
                id="finalizar_parcelas_diario", replace_existing=True, misfire_grace_time=3600, coalesce=True
            )

            # GRUPO B — FARMBOX / MONGODB
            scheduler.add_job(
                job_update_farmbox_mongodb_app, "cron", day_of_week="*", hour="5-19", minute="0",
                id="update_farmbox_apps_hourly", replace_existing=True, misfire_grace_time=1800, coalesce=True
            )

            # GRUPO C — E-MAILS / ALERTAS
            scheduler.add_job(
                job_enviar_email_diario, "cron", day_of_week="mon-fri", hour="6", minute="20",
                id="enviar_email_diario_0620", replace_existing=True, misfire_grace_time=3600
            )
            scheduler.add_job(
                job_enviar_email_alerta_mungo_verde_por_regra, "cron", day_of_week="sun", hour="12", minute="0",
                id="alerta_mungo_verde_domingo_12h", replace_existing=True
            )
            scheduler.add_job(
                job_enviar_email_estoque_farmbox_diario, "cron", day_of_week="*", hour="6", minute="0",
                id="farmbox_stock_report_diario_0600", replace_existing=True
            )

            # GRUPO D — OPSCHECKIN (AGENDA & REMINDERS)
            scheduler.add_job(
                job_run_opscheckin_agenda_0600, "cron", day_of_week="*", hour="6", minute="0",
                id="opscheckin_agenda_0600", replace_existing=True
            )
            scheduler.add_job(
                job_run_opscheckin_reminders, "cron", day_of_week="*", hour="6", minute="15,30,45",
                id="opscheckin_agenda_reminders_early", replace_existing=True
            )
            scheduler.add_job(
                job_run_opscheckin_reminders, "cron", day_of_week="*", hour="7", minute="0",
                id="opscheckin_agenda_reminders_0700", replace_existing=True
            )

            # GRUPO E — OPSCHECKIN (TICKS FREQUENTES)
            scheduler.add_job(
                job_run_opscheckin_agenda_followups, "cron", day_of_week="*", hour="9-18", minute="*/10",
                id="opscheckin_agenda_followups_tick", replace_existing=True
            )
            scheduler.add_job(
                job_run_opscheckin_agenda_confirm, "cron", day_of_week="*", hour="6-18", minute="*/2",
                id="opscheckin_agenda_confirm_tick", replace_existing=True
            )
            scheduler.add_job(
                job_run_opscheckin_director_agenda_summary, "cron", day_of_week="*", hour="7", minute="30",
                id="opscheckin_director_agenda_summary_0730", replace_existing=True
            )
            scheduler.add_job(
                job_run_opscheckin_daily_manager_event_tick, "cron", day_of_week="mon-sat", hour="9-17", minute="*/10",
                id="opscheckin_daily_manager_event_tick", replace_existing=True
            )

            # GRUPO G — MANUTENÇÃO
            scheduler.add_job(
                job_delete_old_job_executions, "cron", day_of_week="*", hour="4", minute="10",
                id="apscheduler_cleanup", replace_existing=True
            )

            # Registra eventos para logar no DB se o DB estiver online
            register_events(scheduler)

            scheduler.start()
            
            # Log de conferência no boot
            logger.info("=== JOBS AGENDADOS (BOOT OK) ===")
            for j in scheduler.get_jobs():
                logger.info(f"ID: {j.id} | Next: {j.next_run_time}")

            return {"ok": True, "scheduler": scheduler}

        return {"ok": False, "reason": "debug_mode"}

    except Exception as e:
        logger.error("Erro fatal ao iniciar scheduler: %s", e, exc_info=True)
        return {"ok": False, "reason": "startup_error", "error": str(e)}