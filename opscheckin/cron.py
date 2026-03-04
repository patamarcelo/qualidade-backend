# opscheckin/cron.py
from django.core.management import call_command

def run_opscheckin_agenda_0600():
    call_command("checkin_tick", "--send-agenda-now")

def run_opscheckin_reminders():
    call_command("checkin_tick")

def run_opscheckin_agenda_followups():
    call_command("agenda_tick")