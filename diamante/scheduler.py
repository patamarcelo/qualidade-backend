# your_app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution
import logging
from diamante.cron import get_hour_test
from diamante.utils import finalizar_parcelas_encerradas, enviar_email_alerta_mungo_verde_por_regra
from diamante.cron import enviar_email_estoque_farmbox_diario
from datetime import datetime

logger = logging.getLogger(__name__)

from importlib import import_module
from django.conf import settings

from diamante.cron import enviar_email_diario

from opscheckin.cron import run_opscheckin_reminders, run_opscheckin_agenda_0600

from django.db import close_old_connections
from .scheduler_lock import acquire_scheduler_lock
from .scheduler_utils import safe_job  # Mantido o import caso seja usado em outro lugar, mas removido dos jobs

import pytz


def get_formatted_datetime():
    now = datetime.now()
    formatted_datetime = now.strftime("%Y_%m_%d_%H_%M_%S")
    return formatted_datetime


def delete_old_job_executions(max_age=604_800):
    """This job deletes APScheduler job execution entries older than `max_age` from the database."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)
    

def get_active_jobs(scheduler, old_id):
    jobs = scheduler.get_jobs()
    logger.info(f"Total active jobs: {len(jobs)}")
    for job in jobs:
        logger.info(f"Job ID: {job.id}, Next Run Time: {job.next_run_time}, Function: {job.func_ref}")
        try:
            print('Job id: ', job.id)
            print('Job id: ', str(job.id))
            print('Job id: ', type(job.id))
            name_old = old_id.replace('_', '')
            job_id_name = str(job.id)
            print('job id founded? ', name_old in job_id_name)
        except Exception as e:
            print('error trying to print job id: ', e)


def start():
    close_old_connections()

    if not acquire_scheduler_lock():
        logger.info("Scheduler não iniciado (lock já está com outro processo).")
        return
    
    try:
        # Fuso horário configurado corretamente
        fuso_horario = pytz.timezone(settings.TIME_ZONE)
        scheduler = BackgroundScheduler(timezone=fuso_horario)
        
        if settings.DEBUG == False:
            module_name, func_name = 'diamante.cron.update_farmbox_mongodb_app'.rsplit('.', 1)
            module = import_module(module_name)
            func = getattr(module, func_name)
            print(f"Funcao encontrada: {func}")
            
            # Conecta o banco de dados ANTES de limpar os jobs
            scheduler.add_jobstore(DjangoJobStore(), "default")
            
            # Limpa a tabela do banco com segurança
            scheduler.remove_all_jobs()
            
            print('agendando funcao para rodar no servidor:')
            date_now = get_formatted_datetime()
            job_id = f'Update_farmbox_apps_Hourly-{date_now}'
            get_active_jobs(scheduler, job_id)
            
            print('job not exists yet, registering....', job_id)
            if settings.ENABLE_CRON_REGISTER:
                
                # CORREÇÃO: safe_job removido de todos os add_job para o pickle conseguir salvar no banco
                
                scheduler.add_job(
                    finalizar_parcelas_encerradas,
                    'cron',
                    day_of_week="*",
                    hour="5",
                    minute="30",
                    id="finalizar_parcelas_diario",
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                
                scheduler.add_job(
                    enviar_email_diario,
                    'cron',
                    day_of_week="mon-fri",
                    hour="6",
                    minute="20",
                    id="enviar_email_diario_0630",
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                
                scheduler.add_job(
                    enviar_email_alerta_mungo_verde_por_regra,
                    'cron',
                    day_of_week='sun',
                    hour=12,
                    minute=0,
                    id='alerta_mungo_verde_domingo_12h',
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                
                scheduler.add_job(
                    enviar_email_estoque_farmbox_diario,
                    'cron',
                    day_of_week="*",
                    hour="6",
                    minute="0",
                    id="farmbox_stock_report_diario_0600",
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                
                scheduler.add_job(
                    run_opscheckin_agenda_0600,
                    "cron",
                    day_of_week="*",
                    hour="9",
                    minute="0",
                    id="opscheckin_agenda_0600",
                    replace_existing=True,
                    misfire_grace_time=600,
                    coalesce=True,
                    max_instances=1,
                )

                scheduler.add_job(
                    run_opscheckin_reminders,
                    "cron",
                    day_of_week="*",
                    hour="9",
                    minute="15,30,45",
                    id="opscheckin_agenda_reminders_0615_0630_0645",
                    replace_existing=True,
                    misfire_grace_time=600,
                    coalesce=True,
                    max_instances=1,
                )

                scheduler.add_job(
                    run_opscheckin_reminders,
                    "cron",
                    day_of_week="*",
                    hour="10",
                    minute="0",
                    id="opscheckin_agenda_reminders_0700",
                    replace_existing=True,
                    misfire_grace_time=600,
                    coalesce=True,
                    max_instances=1,
                )
                
            register_events(scheduler)
            scheduler.start()
            logger.info("Scheduler started successfully with timezone!")
        else:
            print('funcionando, vai rodar somente no servidor')
            
    except Exception as e:
        logger.error(f"Erro fatal ao iniciar o scheduler: {e}", exc_info=True)
        print(f"Erro ao resolver/iniciar as funções do scheduler: {e}")