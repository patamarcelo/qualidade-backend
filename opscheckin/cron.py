# opscheckin/cron.py
from django.core.management import call_command

def opscheckin_tick():
    call_command("checkin_tick")