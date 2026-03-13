from opscheckin.models import Manager


def managers_subscribed(code: str, *, include_inactive: bool = False):
    qs = (
        Manager.objects.filter(
            notification_subscriptions__notification_type__code=code,
            notification_subscriptions__notification_type__is_active=True,
            notification_subscriptions__is_active=True,
        )
        .distinct()
        .order_by("name")
    )

    if not include_inactive:

        # fluxo normal da agenda
        if code == "agenda_prompt":
            qs = qs.filter(is_active=True)

        # resumo para diretores
        elif code == "agenda_summary_director":
            qs = qs.filter(is_active_resume_agenda=True)

        # reuniões diárias
        elif code == "daily_meeting_reminder":
            qs = qs.filter(is_active_for_meetings=True)

        # fallback
        else:
            qs = qs.filter(is_active=True)

    return qs