import logging
import time
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore

from django_apscheduler.jobstores import register_events
from django_apscheduler.models import DjangoJobExecution

from django.conf import settings
from django.db import (
    close_old_connections,
    connection,
    OperationalError,
    InterfaceError,
)

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
    run_opscheckin_manager_personal_reminder_tick,
    run_opscheckin_personal_reminder_coordinator_daily_actions,
)

from maquinario.cron import (
    run_machine_revision_alert_tick,
    run_machine_hourmeter_stale_tick,
)

from .scheduler_lock import acquire_scheduler_lock


logger = logging.getLogger(__name__)


# =====================================================================
# DB HELPERS
# =====================================================================

def _prepare_db_for_job():
    """
    Garante que a conexão com o banco esteja fresca antes de rodar o job.

    Isso é importante porque o APScheduler fica vivo no mesmo processo,
    e conexões antigas do Django podem ficar obsoletas, quebradas ou
    inutilizáveis depois de timeout/restart do Postgres/Railway.
    """
    try:
        close_old_connections()
    except Exception:
        logger.warning(
            "[Scheduler] Falha ao executar close_old_connections antes do job",
            exc_info=True,
        )

    try:
        connection.close_if_unusable_or_obsolete()
    except Exception:
        logger.warning(
            "[Scheduler] Falha ao validar conexão antiga. Fechando conexão.",
            exc_info=True,
        )

        try:
            connection.close()
        except Exception:
            pass


def _close_db_after_job():
    """
    Fecha/limpa conexões após o job.

    Isso reduz o risco de o scheduler segurar uma conexão quebrada
    ou velha para a próxima execução.
    """
    try:
        close_old_connections()
    except Exception:
        pass


def _run_job_with_db_guard(job_name, func, retries=3, delay=5):
    """
    Executa um job com proteção de conexão.

    Inclui:
    - limpeza de conexão antes;
    - retry para OperationalError/InterfaceError;
    - limpeza de conexão depois;
    - logs padronizados.
    """
    last_error = None

    for attempt in range(1, retries + 1):
        _prepare_db_for_job()

        try:
            logger.info(
                "[Scheduler] Iniciando job %s | tentativa %s/%s",
                job_name,
                attempt,
                retries,
            )

            result = func()

            logger.info("[Scheduler] Job %s finalizado com sucesso", job_name)
            return result

        except (OperationalError, InterfaceError) as exc:
            last_error = exc

            logger.warning(
                "[Scheduler] Falha de conexão no job %s | tentativa %s/%s | erro=%s",
                job_name,
                attempt,
                retries,
                exc,
                exc_info=True,
            )

            try:
                connection.close()
            except Exception:
                pass

            if attempt < retries:
                time.sleep(delay)

        except Exception:
            logger.exception("[Scheduler] Erro interno no job %s", job_name)
            raise

        finally:
            _close_db_after_job()

    logger.error(
        "[Scheduler] Job %s falhou após %s tentativas",
        job_name,
        retries,
        exc_info=True,
    )

    raise last_error


def delete_old_job_executions(max_age=604_800):
    """
    Apaga logs antigos de execuções do APScheduler.

    Default: 7 dias.
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


# =====================================================================
# JOB WRAPPERS SERIALIZÁVEIS
# =====================================================================

def job_finalizar_parcelas_encerradas():
    return _run_job_with_db_guard(
        "finalizar_parcelas_encerradas",
        finalizar_parcelas_encerradas,
    )


def job_update_farmbox_mongodb_app():
    return _run_job_with_db_guard(
        "update_farmbox_mongodb_app",
        update_farmbox_mongodb_app,
    )


def job_enviar_email_diario():
    return _run_job_with_db_guard(
        "enviar_email_diario",
        enviar_email_diario,
    )


def job_enviar_email_alerta_mungo_verde_por_regra():
    return _run_job_with_db_guard(
        "enviar_email_alerta_mungo_verde_por_regra",
        enviar_email_alerta_mungo_verde_por_regra,
    )


def job_enviar_email_estoque_farmbox_diario():
    return _run_job_with_db_guard(
        "enviar_email_estoque_farmbox_diario",
        enviar_email_estoque_farmbox_diario,
    )


def job_run_opscheckin_agenda_0600():
    return _run_job_with_db_guard(
        "opscheckin_agenda_0600",
        run_opscheckin_agenda_0600,
    )


def job_run_opscheckin_reminders():
    return _run_job_with_db_guard(
        "opscheckin_reminders",
        run_opscheckin_reminders,
    )


def job_run_opscheckin_agenda_followups():
    return _run_job_with_db_guard(
        "opscheckin_agenda_followups",
        run_opscheckin_agenda_followups,
    )


def job_run_opscheckin_agenda_confirm():
    return _run_job_with_db_guard(
        "opscheckin_agenda_confirm",
        run_opscheckin_agenda_confirm,
    )


def job_run_opscheckin_director_agenda_summary():
    return _run_job_with_db_guard(
        "opscheckin_director_agenda_summary",
        run_opscheckin_director_agenda_summary,
    )


def job_run_opscheckin_daily_manager_event_tick():
    return _run_job_with_db_guard(
        "opscheckin_daily_manager_event_tick",
        run_opscheckin_daily_manager_event_tick,
    )


def job_run_opscheckin_manager_personal_reminder_tick():
    return _run_job_with_db_guard(
        "opscheckin_manager_personal_reminder_tick",
        run_opscheckin_manager_personal_reminder_tick,
    )


def job_run_opscheckin_personal_reminder_coordinator_daily_actions():
    return _run_job_with_db_guard(
        "opscheckin_personal_reminder_coordinator_daily_actions",
        run_opscheckin_personal_reminder_coordinator_daily_actions,
    )


def job_delete_old_job_executions():
    return _run_job_with_db_guard(
        "delete_old_job_executions",
        delete_old_job_executions,
    )


# =====================================================================
# MAQUINÁRIO
# =====================================================================

def job_run_machine_revision_alert_tick():
    return _run_job_with_db_guard(
        "machine_revision_alert_tick",
        run_machine_revision_alert_tick,
    )


def job_run_machine_hourmeter_stale_tick():
    return _run_job_with_db_guard(
        "machine_hourmeter_stale_tick",
        run_machine_hourmeter_stale_tick,
    )


# =====================================================================
# INICIALIZAÇÃO DO SCHEDULER
# =====================================================================

def start():
    _prepare_db_for_job()

    try:
        has_lock = acquire_scheduler_lock(lock_id=777002)
    except Exception as e:
        logger.error(
            "Erro ao adquirir advisory lock do scheduler: %s",
            e,
            exc_info=True,
        )
        return {
            "ok": False,
            "reason": "lock_error",
            "error": str(e),
        }

    if not has_lock:
        logger.info("[Scheduler] Lock já ativo. Scheduler não será iniciado neste processo.")
        return {
            "ok": False,
            "reason": "lock_active",
        }

    try:
        fuso_horario = pytz.timezone(settings.TIME_ZONE)

        # Uso do MemoryJobStore para isolar a agenda das falhas de SSL/Postgres.
        scheduler = BackgroundScheduler(
            timezone=fuso_horario,
            jobstores={
                "default": MemoryJobStore(),
            },
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
        )

        if settings.DEBUG is False:
            logger.info(
                "Agendando jobs (Store: MEMORY) | Timezone: %s",
                settings.TIME_ZONE,
            )

            # =================================================================
            # GRUPO A — FINANCEIRO
            # =================================================================
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

            # =================================================================
            # GRUPO B — FARMBOX / MONGODB
            # =================================================================
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

            # =================================================================
            # GRUPO C — E-MAILS / ALERTAS
            # =================================================================

            # scheduler.add_job(
            #     job_enviar_email_diario,
            #     "cron",
            #     day_of_week="mon-fri",
            #     hour="6",
            #     minute="20",
            #     id="enviar_email_diario_0620",
            #     replace_existing=True,
            #     misfire_grace_time=3600,
            #     coalesce=True,
            #     max_instances=1,
            # )

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

            # =================================================================
            # GRUPO D — OPSCHECKIN (AGENDA & REMINDERS)
            # =================================================================
            scheduler.add_job(
                job_run_opscheckin_agenda_0600,
                "cron",
                day_of_week="*",
                hour="6",
                minute="0",
                id="opscheckin_agenda_0600",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_reminders,
                "cron",
                day_of_week="*",
                hour="6",
                minute="15,30,45",
                id="opscheckin_agenda_reminders_early",
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

            # =================================================================
            # GRUPO E — OPSCHECKIN (TICKS FREQUENTES)
            # =================================================================
            scheduler.add_job(
                job_run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="9-18",
                minute="*/10",
                id="opscheckin_agenda_followups_tick",
                replace_existing=True,
                misfire_grace_time=300,
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
                misfire_grace_time=180,
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
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_daily_manager_event_tick,
                "cron",
                day_of_week="mon-sat",
                hour="9-17",
                minute="*/2",
                id="opscheckin_daily_manager_event_tick",
                replace_existing=True,
                misfire_grace_time=180,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_manager_personal_reminder_tick,
                "cron",
                day_of_week="mon-fri",
                hour="6-18",
                minute="*/10",
                id="opscheckin_manager_personal_reminder_tick",
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_opscheckin_personal_reminder_coordinator_daily_actions,
                "cron",
                day_of_week="mon-fri",
                hour="8",
                minute="30",
                id="opscheckin_personal_reminder_coordinator_daily_actions_0830",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            # =================================================================
            # GRUPO F — MAQUINÁRIO / ALERTAS WHATSAPP
            # =================================================================
            scheduler.add_job(
                job_run_machine_hourmeter_stale_tick,
                "cron",
                day_of_week="mon-fri",
                hour="7",
                minute="10",
                id="machine_hourmeter_stale_tick_0710",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                job_run_machine_revision_alert_tick,
                "cron",
                day_of_week="mon-fri",
                hour="7",
                minute="20",
                id="machine_revision_alert_tick_0720",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            # =================================================================
            # GRUPO G — MANUTENÇÃO
            # =================================================================
            scheduler.add_job(
                job_delete_old_job_executions,
                "cron",
                day_of_week="*",
                hour="4",
                minute="10",
                id="apscheduler_cleanup",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )

            # Registra eventos para logar no DB se o DB estiver online.
            # Protegido para não derrubar o scheduler caso o banco esteja instável no boot.
            try:
                register_events(scheduler)
            except Exception:
                logger.warning(
                    "[Scheduler] Não foi possível registrar eventos do django_apscheduler",
                    exc_info=True,
                )

            scheduler.start()

            logger.info("=== JOBS AGENDADOS (BOOT OK) ===")
            for job in scheduler.get_jobs():
                logger.info("ID: %s | Next: %s", job.id, job.next_run_time)

            return {
                "ok": True,
                "scheduler": scheduler,
            }

        logger.info("[Scheduler] DEBUG=True. Scheduler não iniciado.")
        return {
            "ok": False,
            "reason": "debug_mode",
        }

    except Exception as e:
        logger.error(
            "Erro fatal ao iniciar scheduler: %s",
            e,
            exc_info=True,
        )
        return {
            "ok": False,
            "reason": "startup_error",
            "error": str(e),
        }