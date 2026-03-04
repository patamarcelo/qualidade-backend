# your_app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution
import logging
from diamante.utils import finalizar_parcelas_encerradas, enviar_email_alerta_mungo_verde_por_regra
from diamante.cron import enviar_email_estoque_farmbox_diario, enviar_email_diario
from datetime import datetime

logger = logging.getLogger(__name__)

from importlib import import_module
from django.conf import settings

from opscheckin.cron import (
    run_opscheckin_agenda_0600,      # ✅ pergunta de agenda (template) 06:00
    run_opscheckin_reminders,        # ✅ reminders cravados 06:15/06:30/06:45/07:00
    run_opscheckin_agenda_followups, # ✅ follow-up itens (botões) 09/11/13/15/17
)

from django.db import close_old_connections
from .scheduler_lock import acquire_scheduler_lock

import pytz


def get_formatted_datetime():
    now = datetime.now()
    return now.strftime("%Y_%m_%d_%H_%M_%S")


def delete_old_job_executions(max_age=604_800):
    """Apaga logs antigos de execuções do APScheduler (default: 7 dias)."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


def get_active_jobs(scheduler, old_id):
    jobs = scheduler.get_jobs()
    logger.info(f"Total active jobs: {len(jobs)}")
    for job in jobs:
        logger.info(f"Job ID: {job.id}, Next Run Time: {job.next_run_time}, Function: {job.func_ref}")
        try:
            name_old = old_id.replace("_", "")
            job_id_name = str(job.id)
            logger.info("job id founded? %s", name_old in job_id_name)
        except Exception as e:
            logger.warning("error trying to print job id: %s", e)


def start():
    close_old_connections()

    if not acquire_scheduler_lock():
        logger.info("Scheduler não iniciado (lock já está com outro processo).")
        return

    try:
        # ✅ Fuso horário correto do Django (ex: America/Sao_Paulo)
        fuso_horario = pytz.timezone(settings.TIME_ZONE)
        scheduler = BackgroundScheduler(timezone=fuso_horario)

        if settings.DEBUG is False:
            # Conecta o banco de dados ANTES de mexer nos jobs
            scheduler.add_jobstore(DjangoJobStore(), "default")

            # Limpa jobs existentes (você já optou por sempre recriar)
            scheduler.remove_all_jobs()

            logger.info("Agendando jobs no servidor…")

            # =====================================================================
            # GRUPO A — ROTINAS FINANCEIRAS / PARCELAS (Diamante)
            # =====================================================================
            scheduler.add_job(
                finalizar_parcelas_encerradas,
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
            # GRUPO B — E-MAILS / ALERTAS (Diamante)
            # =====================================================================
            scheduler.add_job(
                enviar_email_diario,
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
                enviar_email_alerta_mungo_verde_por_regra,
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
                enviar_email_estoque_farmbox_diario,
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
            # GRUPO C — OPSCHECKIN (WhatsApp) — AGENDA + REMINDERS (Templates)
            # =====================================================================
            # 06:00 — dispara a pergunta de agenda (template "AGENDA")
            scheduler.add_job(
                run_opscheckin_agenda_0600,
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

            # 06:15 / 06:30 / 06:45 — reminders (template "REMINDER")
            scheduler.add_job(
                run_opscheckin_reminders,
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

            # 07:00 — reminder final
            scheduler.add_job(
                run_opscheckin_reminders,
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
            # GRUPO D — OPSCHECKIN (WhatsApp) — FOLLOW-UP DOS ITENS (Botões)
            # =====================================================================
            # A cada 2 horas (até 17:00) — acompanha itens "open" com botões:
            # 09:00, 11:00, 13:00, 15:00, 17:00
            # (lembrando: botões/interactive exigem janela de 24h aberta)
            scheduler.add_job(
                run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="9",
                minute="0",
                id="opscheckin_agenda_followup_0900",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="11",
                minute="0",
                id="opscheckin_agenda_followup_1100",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="13",
                minute="0",
                id="opscheckin_agenda_followup_1300",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="15",
                minute="0",
                id="opscheckin_agenda_followup_1500",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            scheduler.add_job(
                run_opscheckin_agenda_followups,
                "cron",
                day_of_week="*",
                hour="17",
                minute="0",
                id="opscheckin_agenda_followup_1700",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )

            # =====================================================================
            # GRUPO E — MANUTENÇÃO APSCHEDULER (limpeza de logs)
            # =====================================================================
            scheduler.add_job(
                delete_old_job_executions,
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

            # Eventos do APScheduler (executions, errors, etc)
            register_events(scheduler)

            scheduler.start()
            logger.info("Scheduler started successfully with timezone=%s", settings.TIME_ZONE)

        else:
            logger.info("DEBUG=True: scheduler não será iniciado localmente (rodará apenas no servidor).")

    except Exception as e:
        logger.error("Erro fatal ao iniciar o scheduler: %s", e, exc_info=True)
        print(f"Erro ao resolver/iniciar as funções do scheduler: {e}")