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
        # Regra obrigatória para qualquer tipo de notificação
        qs = qs.filter(is_active=True)

        # Regra adicional para resumo dos diretores
        if code == "agenda_summary_director":
            qs = qs.filter(is_active_resume_agenda=True)

        # Regra adicional para reuniões diárias
        elif code == "daily_meeting_reminder":
            qs = qs.filter(is_active_for_meetings=True)

    return qs