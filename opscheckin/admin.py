# opscheckin/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import Manager, DailyCheckin, OutboundQuestion, InboundMessage


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone_e164", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone_e164")
    ordering = ("name",)


class OutboundQuestionInline(admin.TabularInline):
    model = OutboundQuestion
    extra = 0
    readonly_fields = ("sent_at", "answered_at", "last_reminder_at")
    fields = ("step", "status", "scheduled_for", "sent_at", "answered_at", "reminder_count")
    ordering = ("scheduled_for",)


class InboundMessageInline(admin.TabularInline):
    model = InboundMessage
    extra = 0
    readonly_fields = ("received_at", "from_phone", "wa_message_id", "msg_type", "text", "linked_question")
    fields = ("received_at", "msg_type", "text", "linked_question")
    ordering = ("-received_at",)


@admin.register(DailyCheckin)
class DailyCheckinAdmin(admin.ModelAdmin):
    list_display = ("id", "manager", "date", "created_at", "questions_count", "inbound_count")
    list_filter = ("date", "manager")
    search_fields = ("manager__name", "manager__phone_e164")
    date_hierarchy = "date"
    ordering = ("-date", "-id")
    inlines = [OutboundQuestionInline, InboundMessageInline]

    def questions_count(self, obj):
        return obj.questions.count()

    def inbound_count(self, obj):
        return obj.inbound_messages.count()


@admin.register(OutboundQuestion)
class OutboundQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "checkin",
        "step",
        "status",
        "scheduled_for",
        "sent_at",
        "answered_at",
        "reminder_count",
        "short_answer",
    )
    list_filter = ("status", "step", "checkin__date")
    search_fields = ("checkin__manager__name", "checkin__manager__phone_e164", "answer_text")
    ordering = ("-scheduled_for", "-id")
    readonly_fields = ("sent_at", "answered_at", "last_reminder_at")

    def short_answer(self, obj):
        a = (obj.answer_text or "").strip()
        if not a:
            return "-"
        return (a[:80] + "…") if len(a) > 80 else a


@admin.register(InboundMessage)
class InboundMessageAdmin(admin.ModelAdmin):
    """
    Inbox do WhatsApp: tudo que chegou, com ou sem pergunta pendente.
    """
    list_display = (
        "id",
        "received_at",
        "manager",
        "from_phone",
        "msg_type",
        "linked_question",
        "short_text",
        "processed",
    )
    list_filter = ("processed", "msg_type", "manager", "received_at")
    search_fields = ("from_phone", "text", "wa_message_id", "manager__name")
    ordering = ("-received_at", "-id")
    readonly_fields = ("received_at",)

    def short_text(self, obj):
        t = (obj.text or "").strip()
        return (t[:120] + "…") if len(t) > 120 else t