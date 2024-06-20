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
        scheduler = BackgroundScheduler()
        # remove all runing jobs
        scheduler.remove_all_jobs()
        if settings.DEBUG == False:
            module_name, func_name = 'diamante.cron.update_farmbox_mongodb_app'.rsplit('.', 1)
            module = import_module(module_name)
            func = getattr(module, func_name)
            print(f"Funcao encontrada: {func}")
            scheduler.add_jobstore(DjangoJobStore(), "default")
            print('agendando funcao para rodar no servidor:')
            # Register the job with a textual reference
            job_id = "Update_farmbox_apps_Hourly"
            existing_job = scheduler.get_job(job_id)
            print(f'existing job: ID:{job_id} - job_Instance: {existing_job}')
            if existing_job:
                print('job already registered', job_id)
                existing_job.modify(
                    func,
                    'cron',
                    # day_of_week="*",
                    day_of_week="mon-sat",
                    hour="5-19",  # From 5 AM to 7:59 PM
                    # minute="15,30,45,58",  # At 15, 30, 45 and 58 minutes of each hour
                    minute="59",  # At 15, 30, 45 and 58 minutes of each hour
                    id=job_id
                )
            else:
                print('job not exists yet, registering....', job_id)
                scheduler.add_job(
                    func,
                    'cron',
                    day_of_week="*",
                    hour="5-19",  # From 6 AM to 7:59 PM
                    minute="59",  # At 15, 30, 45 and 58 minutes of each hour
                    id=job_id
                )
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
        else:
            print('funcionando, vai rodar somente no servidor')
    except Exception as e:
        print(f"Error resolving function: {e}")
