# maquinario/cron.py

from django.core.management import call_command


def run_machine_revision_alert_tick():
    return call_command("machine_revision_alert_tick")


def run_machine_hourmeter_stale_tick():
    return call_command("machine_hourmeter_stale_tick", days=4)