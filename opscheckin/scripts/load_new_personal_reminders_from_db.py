from django.db import transaction
from opscheckin.models import (
    Manager,
    NotificationType,
    ManagerNotificationSubscription,
    ManagerPersonalReminder,
)

SOURCE_MANAGER_ID = 1
TARGET_MANAGER_ID = 17

with transaction.atomic():
    source_manager = Manager.objects.get(id=SOURCE_MANAGER_ID)
    target_manager = Manager.objects.get(id=TARGET_MANAGER_ID)

    # Garante que o manager destino também esteja inscrito no tipo de notificação
    nt, _ = NotificationType.objects.get_or_create(
        code="personal_reminder",
        defaults={
            "name": "Avisos pessoais",
            "description": "Recebe lembretes pessoais recorrentes do manager",
            "is_active": True,
        },
    )

    ManagerNotificationSubscription.objects.update_or_create(
        manager=target_manager,
        notification_type=nt,
        defaults={"is_active": True},
    )

    source_reminders = list(
        ManagerPersonalReminder.objects
        .filter(manager=source_manager)
        .order_by("id")
    )

    created_ids = []

    for reminder in source_reminders:
        reminder.pk = None
        reminder.id = None
        reminder.manager = target_manager
        reminder.save()

        created_ids.append(reminder.id)

    deleted_count, deleted_detail = ManagerPersonalReminder.objects.filter(
        manager=source_manager
    ).delete()

print("source_manager:", source_manager.id, source_manager.name)
print("target_manager:", target_manager.id, target_manager.name)
print("copied:", len(created_ids))
print("created_ids:", created_ids)
print("deleted_count:", deleted_count)
print("deleted_detail:", deleted_detail)