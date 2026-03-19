from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution

import logging
from datetime import datetime

from django.conf import settings
from django.db import close_old_connections, connection

import pytz

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


def get_formatted_datetime():
    now = datetime.now()
    return now.strftime("%Y_%m_%d_%H_%M_%S")


def delete_old_job_executions(max_age=604_800):
    """
    Apaga logs antigos de execuções do APScheduler (default: 7 dias).
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


def _prepare_db_for_job():
    close_old_connections()
    connection.close_if_unusable_or_obsolete()


# =====================================================================
# JOB WRAPPERS SERIALIZÁVEIS
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


def start():
    close_old_connections()
    connection.close_if_unusable_or_obsolete()

    try:
        has_lock = acquire_scheduler_lock()
    except Exception as e:
        logger.error(
            "Erro ao adquirir advisory lock do scheduler: %s", e, exc_info=True
        )
        return {
            "ok": False,
            "reason": "lock_error",
            "error": str(e),
        }

    if not has_lock:
        logger.warning(
            "Scheduler não iniciado: advisory lock já está ativo em outro processo."
        )
        return {
            "ok": False,
            "reason": "lock_active",
        }

    try:
        fuso_horario = pytz.timezone(settings.TIME_ZONE)
        scheduler = BackgroundScheduler(timezone=fuso_horario)

        if settings.DEBUG is False:
            scheduler.add_jobstore(DjangoJobStore(), "default")

            logger.info("Agendando jobs no servidor… timezone=%s", settings.TIME_ZONE)

            # =====================================================================
            # GRUPO A — ROTINAS FINANCEIRAS / PARCELAS (Diamante)
            # =====================================================================
            scheduler.add_job(
                job_finalizar_parcelas_encerradas,
                "cron",
                day_of_week="*",
                hour="5",
                minute="30",
                id="finalizar_parcelas_diario",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO B — FARMBOX / MONGODB
            # Regra: rodar todos os dias, de hora em hora, das 05:00 às 19:00
            # =====================================================================
            scheduler.add_job(
                job_update_farmbox_mongodb_app,
                "cron",
                day_of_week="*",
                hour="5-19",
                minute="0",
                id="update_farmbox_apps_hourly",
                replace_existing=True,
                misfire_grace_time=1800,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO C — E-MAILS / ALERTAS (Diamante)
            # =====================================================================
            scheduler.add_job(
                job_enviar_email_diario,
                "cron",
                day_of_week="mon-fri",
                hour="6",
                minute="20",
                id="enviar_email_diario_0620",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_enviar_email_alerta_mungo_verde_por_regra,
                "cron",
                day_of_week="sun",
                hour="12",
                minute="0",
                id="alerta_mungo_verde_domingo_12h",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_enviar_email_estoque_farmbox_diario,
                "cron",
                day_of_week="*",
                hour="6",
                minute="0",
                id="farmbox_stock_report_diario_0600",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO D — OPSCHECKIN (WhatsApp) — AGENDA + REMINDERS
            # =====================================================================
            scheduler.add_job(
                job_run_opscheckin_agenda_0600,
                "cron",
                day_of_week="*",
                hour="6",
                minute="0",
                id="opscheckin_agenda_0600",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_reminders,
                "cron",
                day_of_week="*",
                hour="6",
                minute="15,30,45",
                id="opscheckin_agenda_reminders_0615_0630_0645",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_reminders,
                "cron",
                day_of_week="*",
                hour="7",
                minute="0",
                id="opscheckin_agenda_reminders_0700",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO E — OPSCHECKIN (WhatsApp) — FOLLOW-UP DO DIA
            # =====================================================================
            scheduler.add_job(
                job_run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="9-18",
                minute="*/10",
                id="opscheckin_agenda_followups_tick_0917_10min",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_agenda_confirm,
                "cron",
                day_of_week="*",
                hour="6-18",
                minute="*/2",
                id="opscheckin_agenda_confirm_tick",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_director_agenda_summary,
                "cron",
                day_of_week="*",
                hour="7",
                minute="30",
                id="opscheckin_director_agenda_summary_0730",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO F — OPSCHECKIN (WhatsApp) — LEMBRETE REUNIÃO DIÁRIA
            # =====================================================================
            scheduler.add_job(
                job_run_opscheckin_daily_manager_event_tick,
                "cron",
                day_of_week="mon-sat",
                hour="9-17",
                minute="*/10",
                id="opscheckin_daily_manager_event_tick_10min_0916",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO G — MANUTENÇÃO APSCHEDULER
            # =====================================================================
            scheduler.add_job(
                job_delete_old_job_executions,
                "cron",
                day_of_week="*",
                hour="4",
                minute="10",
                id="apscheduler_cleanup_old_executions",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            register_events(scheduler)

            scheduler.start()
            logger.info("Scheduler started successfully with DjangoJobStore.")
            return {
                "ok": True,
                "scheduler": scheduler,
            }

        logger.info(
            "DEBUG=True: scheduler não será iniciado localmente (rodará apenas no servidor)."
        )
        return {
            "ok": False,
            "reason": "debug_mode",
        }

    except Exception as e:
        logger.error("Erro fatal ao iniciar o scheduler: %s", e, exc_info=True)
        print(f"Erro ao resolver/iniciar as funções do scheduler: {e}")
        return {
            "ok": False,
            "reason": "startup_error",
            "error": str(e),
        }
