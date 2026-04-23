from django.core.management import call_command
from django.db import connection

# Grupo: envio inicial da agenda (06:00)
def run_opscheckin_agenda_0600():
    connection.close()
    call_command("checkin_tick", "--send-agenda-now")

# Grupo: reminders da agenda (06:15/06:30/06:45/07:00)
def run_opscheckin_reminders():
    connection.close()
    call_command("checkin_tick")

# Grupo: confirmação 10 min após resposta da agenda + auto-ok por silêncio
def run_opscheckin_agenda_confirm():
    connection.close()
    call_command("agenda_confirm_tick")

# Grupo: followups 90/90 até 17h (perguntar qual item foi concluído)
def run_opscheckin_agenda_followups():
    from django.utils import timezone
    import logging

    logger = logging.getLogger("opscheckin.followups")
    connection.close()
    logger.warning("FOLLOWUP_TICK %s", timezone.now())
    call_command("agenda_tick")

def run_opscheckin_director_agenda_summary():
    connection.close()
    call_command("director_agenda_summary_tick")

def run_opscheckin_daily_manager_event_tick():
    connection.close()
    call_command("daily_manager_event_tick")

def run_opscheckin_manager_personal_reminder_tick():
    connection.close()
    call_command("manager_personal_reminder_tick")