# from apscheduler.schedulers.background import BackgroundScheduler
# from django_apscheduler.jobstores import DjangoJobStore
# from django_apscheduler import register_events
# from django.utils import timezone

# from .models import Manager
# from .services.flow import create_and_send_next_question
# from .services.reminders import process_reminders


# def start():
#     scheduler = BackgroundScheduler(timezone=str(timezone.get_current_timezone()))
#     scheduler.add_jobstore(DjangoJobStore(), "default")

#     # 6:00 — dispara AGENDA
#     scheduler.add_job(run_daily_agenda, "cron", hour=6, minute=0)

#     # a cada 10 minutos — reminders
#     scheduler.add_job(process_reminders, "interval", minutes=10)

#     register_events(scheduler)
#     scheduler.start()


# def run_daily_agenda():
#     managers = Manager.objects.filter(is_active=True)
#     for m in managers:
#         create_and_send_next_question(m)