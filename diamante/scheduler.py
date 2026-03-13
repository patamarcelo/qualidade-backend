# your_app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution

import logging
from datetime import datetime

from django.conf import settings
from django.db import close_old_connections

import pytz

from diamante.utils import finalizar_parcelas_encerradas, enviar_email_alerta_mungo_verde_por_regra
from diamante.cron import enviar_email_estoque_farmbox_diario, enviar_email_diario

from opscheckin.cron import (
    run_opscheckin_agenda_0600,       # ✅ pergunta de agenda (template) 06:00
    run_opscheckin_reminders,         # ✅ reminders cravados 06:15/06:30/06:45/07:00
    run_opscheckin_agenda_followups,  # ✅ follow-up (tick) itens/agenda durante o dia
    run_opscheckin_agenda_confirm,   # ✅ ADD
    run_opscheckin_director_agenda_summary,
    run_opscheckin_daily_manager_event_tick

)

from .scheduler_lock import acquire_scheduler_lock

logger = logging.getLogger(__name__)


def get_formatted_datetime():
    now = datetime.now()
    return now.strftime("%Y_%m_%d_%H_%M_%S")


def delete_old_job_executions(max_age=604_800):
    """
    Apaga logs antigos de execuções do APScheduler (default: 7 dias).
    Mantém a tabela django_apscheduler mais leve.
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


def start():
    close_old_connections()

    # Evita múltiplos schedulers em múltiplas instâncias/processos
    if not acquire_scheduler_lock():
        logger.info("Scheduler não iniciado (lock já está com outro processo).")
        return

    try:
        fuso_horario = pytz.timezone(settings.TIME_ZONE)  # ex: America/Sao_Paulo
        scheduler = BackgroundScheduler(timezone=fuso_horario)

        if settings.DEBUG is False:
            # Conecta jobstore no banco antes de cadastrar jobs
            scheduler.add_jobstore(DjangoJobStore(), "default")

            # Você optou por sempre recriar tudo
            scheduler.remove_all_jobs()
            logger.info("Agendando jobs no servidor… timezone=%s", settings.TIME_ZONE)

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
            # 06:00 — dispara a pergunta de agenda (TEMPLATE "AGENDA")
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

            # 06:15 / 06:30 / 06:45 — reminders (TEMPLATE "REMINDER")
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

            # 07:00 — reminder final (TEMPLATE "REMINDER")
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
            # GRUPO D — OPSCHECKIN (WhatsApp) — FOLLOW-UP DO DIA (tick “inteligente”)
            # =====================================================================
            # Aqui NÃO tentamos “90 em 90” no cron.
            # Rodamos um tick em janelas fixas (ex: a cada 30 min),
            # e o comando decide por manager:
            #  - mandar confirmação 10min após receber agenda (se pendente)
            #  - mandar follow-up a cada 90min até 17h
            #  - respeitar cooldown (não spammar)
            #
            # Se quiser mais responsivo: minute="*/10" (a cada 10 min).
            scheduler.add_job(
                run_opscheckin_agenda_followups,
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
                run_opscheckin_agenda_confirm,
                "cron",
                day_of_week="*",
                hour="6-18",
                minute="*/2",  # a cada 2 min (pode ser */1 se quiser bem responsivo)
                id="opscheckin_agenda_confirm_tick",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )
            scheduler.add_job(
                run_opscheckin_director_agenda_summary,
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
            # GRUPO E — OPSCHECKIN (WhatsApp) — LEMBRETE REUNIÃO DIÁRIA
            # =====================================================================
            # Roda de hora em hora, de segunda a sábado, das 9h às 16h.
            # A lógica interna decide:
            #  - horário efetivo do evento (default ou override do dia)
            #  - se falta <= 90 min para a reunião
            #  - se já entrou na janela de disparo (ex.: 60 min antes)
            #  - se já enviou hoje para cada manager
            scheduler.add_job(
                run_opscheckin_daily_manager_event_tick,
                "cron",
                day_of_week="mon-sat",
                hour="9-16",
                minute="0",
                id="opscheckin_daily_manager_event_tick_hourly_0916",
                replace_existing=True,
                misfire_grace_time=600,
                coalesce=True,
                max_instances=1,
            )
            # =====================================================================
            # GRUPO E — MANUTENÇÃO APSCHEDULER
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

            # Eventos do APScheduler (logs / erros)
            register_events(scheduler)

            scheduler.start()
            logger.info("Scheduler started successfully with timezone=%s", settings.TIME_ZONE)

        else:
            logger.info("DEBUG=True: scheduler não será iniciado localmente (rodará apenas no servidor).")

    except Exception as e:
        logger.error("Erro fatal ao iniciar o scheduler: %s", e, exc_info=True)
        print(f"Erro ao resolver/iniciar as funções do scheduler: {e}")