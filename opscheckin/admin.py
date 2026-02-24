# opscheckin/admin.py
from django.contrib import admin
from django.utils import timezone
from django.db.models import Q

from .models import Manager, DailyCheckin, OutboundQuestion


# ---------- Helpers ----------
def _local_dt(dt):
    if not dt:
        return "-"
    return timezone.localtime(dt).strftime("%d/%m %H:%M")


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_e164", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone_e164")
    ordering = ("name",)


class OutboundQuestionInline(admin.TabularInline):
    model = OutboundQuestion
    extra = 0
    fields = (
        "step",
        "scheduled_for",
        "status",
        "sent_at",
        "answered_at",
        "reminder_count",
        "answer_text",
    )
    readonly_fields = ("sent_at", "answered_at")
    show_change_link = True


@admin.register(DailyCheckin)
class DailyCheckinAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "manager",
        "summary_status",
        "answered_count",
        "pending_count",
        "missed_count",
        "created_at",
    )
    list_filter = ("date", "manager")
    search_fields = ("manager__name", "manager__phone_e164")
    date_hierarchy = "date"
    ordering = ("-date", "manager__name")
    inlines = [OutboundQuestionInline]

    def summary_status(self, obj):
        qs = obj.questions.all()
        if qs.filter(status="pending").exists():
            return "🟡 PENDING"
        if qs.filter(status="missed").exists():
            return "🔴 MISSED"
        if qs.filter(status="answered").exists() and qs.count() > 0:
            return "🟢 DONE"
        return "⚪️ EMPTY"

    summary_status.short_description = "Status"

    def answered_count(self, obj):
        return obj.questions.filter(status="answered").count()

    answered_count.short_description = "Answered"

    def pending_count(self, obj):
        return obj.questions.filter(status="pending").count()

    pending_count.short_description = "Pending"

    def missed_count(self, obj):
        return obj.questions.filter(status="missed").count()

    missed_count.short_description = "Missed"

    def get_list_display(self, request):
        base = list(self.list_display)
        if not hasattr(DailyCheckin, "created_at"):
            base.remove("created_at")
        return tuple(base)


@admin.register(OutboundQuestion)
class OutboundQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "manager",
        "step",
        "status",
        "scheduled_for",
        "sent_at_local",
        "answered_at_local",
        "reminder_count",
        "answer_preview",
    )
    list_filter = ("status", "step", "checkin__date", "checkin__manager")
    search_fields = (
        "checkin__manager__name",
        "checkin__manager__phone_e164",
        "answer_text",
        "step",
    )
    ordering = ("-checkin__date", "checkin__manager__name", "scheduled_for")
    date_hierarchy = "checkin__date"
    readonly_fields = (
        "checkin",
        "step",
        "scheduled_for",
        "sent_at",
        "answered_at",
        "reminder_count",
        "last_reminder_at",
    )
    actions = ("mark_as_missed", "mark_as_pending", "clear_answer")

    def date(self, obj):
        return obj.checkin.date

    date.admin_order_field = "checkin__date"

    def manager(self, obj):
        return obj.checkin.manager

    manager.admin_order_field = "checkin__manager__name"

    def sent_at_local(self, obj):
        return _local_dt(obj.sent_at)

    sent_at_local.short_description = "Sent (local)"
    sent_at_local.admin_order_field = "sent_at"

    def answered_at_local(self, obj):
        return _local_dt(obj.answered_at)

    answered_at_local.short_description = "Answered (local)"
    answered_at_local.admin_order_field = "answered_at"

    def answer_preview(self, obj):
        if not obj.answer_text:
            return "-"
        txt = obj.answer_text.strip().replace("\n", " ")
        return (txt[:60] + "…") if len(txt) > 60 else txt

    answer_preview.short_description = "Answer"

    @admin.action(description="Mark selected as MISSED")
    def mark_as_missed(self, request, queryset):
        queryset.update(status="missed")

    @admin.action(description="Mark selected as PENDING (reopen)")
    def mark_as_pending(self, request, queryset):
        queryset.update(status="pending", answered_at=None)

    @admin.action(description="Clear answer (keep status)")
    def clear_answer(self, request, queryset):
        queryset.update(answer_text="")

    # Filtro rápido “Hoje”
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("checkin", "checkin__manager")