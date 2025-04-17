# your_app/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution
import logging
from diamante.cron import get_hour_test

from datetime import datetime

logger = logging.getLogger(__name__)

from importlib import import_module
from django.conf import settings



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
            date_now = get_formatted_datetime()
            job_id=f'Update_farmbox_apps_Hourly-{date_now}'
            get_active_jobs(scheduler, job_id)
            # if existing_job:
            #     print('job already registered', job_id)
            #     existing_job.modify(
            #         func,
            #         'cron',
            #         # day_of_week="*",
            #         day_of_week="mon-sat",
            #         hour="5-19",  # From 5 AM to 7:59 PM
            #         # minute="15,30,45,58",  # At 15, 30, 45 and 58 minutes of each hour
            #         minute="59",  # At 15, 30, 45 and 58 minutes of each hour
            #         id=job_id
            #     )
            # else:
            print('job not exists yet, registering....', job_id)
            scheduler.add_job(
                func,
                'cron',
                day_of_week="*",
                hour="5-19",  # From 6 AM to 7:59 PM
                minute="58",  # At 15, 30, 45 and 58 minutes of each hour
                id=job_id,
                replace_existing=True,
                misfire_grace_time=30  # segundos de tolerância para atraso

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
