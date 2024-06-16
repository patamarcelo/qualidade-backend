# your_app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution
import logging
from diamante.cron import get_hour_test

logger = logging.getLogger(__name__)

from importlib import import_module
from django.conf import settings





def delete_old_job_executions(max_age=604_800):
    """This job deletes APScheduler job execution entries older than `max_age` from the database."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)

def start():
    try:
        module_name, func_name = 'diamante.cron.get_hour_test'.rsplit('.', 1)
        module = import_module(module_name)
        func = getattr(module, func_name)
        print(f"Funcao encontrada: {func}")
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        if settings.DEBUG == True:
            print('agendando funcao para rodar no servidor:')
            # Register the job with a textual reference
            scheduler.add_job(
                func,
                'cron',
                day_of_week="*",
                hour="*",
                minute="*",
                id="Imprimindo a cada segundo no servidor LOCAL"
            )
        else:
            print('funcionando, vai rodar somente no servidor')
        register_events(scheduler)
        scheduler.start()
        logger.info("Scheduler started!")

        # Cleanup old job executions
        scheduler.add_job(
            delete_old_job_executions,
            trigger='interval',
            days=7,
            id='delete_old_job_executions',
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Added job: 'delete_old_job_executions'.")
    except Exception as e:
        print(f"Error resolving function: {e}")
