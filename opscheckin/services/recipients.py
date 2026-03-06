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
        qs = qs.filter(is_active=True)

    return qs