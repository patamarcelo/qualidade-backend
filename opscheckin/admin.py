from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone

from .models import Manager, DailyCheckin, OutboundQuestion, InboundMessage


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone_e164", "is_active", "last_checkin_link")
    list_filter = ("is_active",)
    search_fields = ("name", "phone_e164")
    ordering = ("name",)

    def last_checkin_link(self, obj):
        last = obj.checkins.order_by("-date", "-id").first()
        if not last:
            return "-"
        url = reverse("admin:opscheckin_dailycheckin_change", args=[last.id])
        return format_html('<a href="{}">{} ({})</a>', url, last.date, last.questions.count())

    last_checkin_link.short_description = "Último check-in"


class OutboundQuestionInline(admin.TabularInline):
    model = OutboundQuestion
    extra = 0
    readonly_fields = ("sent_at", "answered_at", "last_reminder_at", "short_answer")
    fields = (
        "step",
        "status",
        "scheduled_for",
        "sent_at",
        "answered_at",
        "reminder_count",
        "short_answer",
    )
    ordering = ("scheduled_for",)

    def short_answer(self, obj):
        a = (obj.answer_text or "").strip()
        if not a:
            return "-"
        return (a[:80] + "…") if len(a) > 80 else a

    short_answer.short_description = "Resposta"


class InboundMessageInline(admin.TabularInline):
    model = InboundMessage
    extra = 0
    readonly_fields = ("received_at", "from_phone", "wa_message_id", "msg_type", "text", "linked_question_link", "processed")
    fields = ("received_at", "msg_type", "text", "linked_question_link", "processed")
    ordering = ("-received_at",)

    def linked_question_link(self, obj):
        if not obj.linked_question_id:
            return "-"
        url = reverse("admin:opscheckin_outboundquestion_change", args=[obj.linked_question_id])
        q = obj.linked_question
        return format_html('<a href="{}">{} • {}</a>', url, q.step, q.status)

    linked_question_link.short_description = "Pergunta"


@admin.register(DailyCheckin)
class DailyCheckinAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "manager",
        "date",
        "created_at",
        "day_status",
        "questions_count",
        "pending_sent_count",
        "answered_count",
        "missed_count",
        "inbound_count",
    )
    list_filter = ("date", "manager", "manager__is_active")
    search_fields = ("manager__name", "manager__phone_e164")
    date_hierarchy = "date"
    ordering = ("-date", "-id")
    inlines = [OutboundQuestionInline, InboundMessageInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("manager")
        qs = qs.annotate(
            questions_total=Count("questions", distinct=True),
            inbound_total=Count("inbound_messages", distinct=True),
            answered_total=Count("questions", filter=Q(questions__status="answered"), distinct=True),
            missed_total=Count("questions", filter=Q(questions__status="missed"), distinct=True),
            pending_sent_total=Count(
                "questions",
                filter=Q(questions__status="pending", questions__sent_at__isnull=False, questions__answered_at__isnull=True),
                distinct=True,
            ),
        )
        return qs

    def questions_count(self, obj):
        return getattr(obj, "questions_total", obj.questions.count())
    questions_count.short_description = "Perguntas"

    def inbound_count(self, obj):
        return getattr(obj, "inbound_total", obj.inbound_messages.count())
    inbound_count.short_description = "Inbounds"

    def answered_count(self, obj):
        return getattr(obj, "answered_total", obj.questions.filter(status="answered").count())
    answered_count.short_description = "Answered"

    def missed_count(self, obj):
        return getattr(obj, "missed_total", obj.questions.filter(status="missed").count())
    missed_count.short_description = "Missed"

    def pending_sent_count(self, obj):
        return getattr(obj, "pending_sent_total", obj.questions.filter(status="pending", sent_at__isnull=False, answered_at__isnull=True).count())
    pending_sent_count.short_description = "Pendentes (enviadas)"

    def day_status(self, obj):
        # regra simples para o admin: se tem pending enviada -> "Em aberto"
        pending_sent = getattr(obj, "pending_sent_total", None)
        missed = getattr(obj, "missed_total", None)

        if pending_sent is None:
            pending_sent = obj.questions.filter(status="pending", sent_at__isnull=False, answered_at__isnull=True).count()
        if missed is None:
            missed = obj.questions.filter(status="missed").count()

        if pending_sent > 0:
            return format_html('<span style="color:#f59e0b;font-weight:700;">Em aberto</span>')
        if missed > 0:
            return format_html('<span style="color:#ef4444;font-weight:700;">Missed</span>')
        # se tem perguntas e nenhuma pendente enviada/missed -> ok
        if obj.questions.exists():
            return format_html('<span style="color:#22c55e;font-weight:700;">OK</span>')
        return "-"
    day_status.short_description = "Status do dia"


@admin.register(OutboundQuestion)
class OutboundQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "checkin_link",
        "step",
        "status",
        "scheduled_for",
        "sent_at",
        "answered_at",
        "reminder_count",
        "answer_len",
        "short_answer",
        "time_to_answer",
    )
    list_filter = ("status", "step", "checkin__date")
    search_fields = ("checkin__manager__name", "checkin__manager__phone_e164", "answer_text")
    ordering = ("-scheduled_for", "-id")
    readonly_fields = ("sent_at", "answered_at", "last_reminder_at")

    def checkin_link(self, obj):
        url = reverse("admin:opscheckin_dailycheckin_change", args=[obj.checkin_id])
        return format_html('<a href="{}">{}</a>', url, str(obj.checkin))
    checkin_link.short_description = "Checkin"

    def short_answer(self, obj):
        a = (obj.answer_text or "").strip()
        if not a:
            return "-"
        return (a[:80] + "…") if len(a) > 80 else a
    short_answer.short_description = "Resposta"

    def answer_len(self, obj):
        return len((obj.answer_text or "").strip())
    answer_len.short_description = "Chars"

    def time_to_answer(self, obj):
        if not obj.sent_at or not obj.answered_at:
            return "-"
        delta = obj.answered_at - obj.sent_at
        mins = int(delta.total_seconds() // 60)
        return f"{mins} min"
    time_to_answer.short_description = "T. resposta"


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
        "linked_question_link",
        "short_text",
        "processed",
    )
    list_filter = ("processed", "msg_type", "manager")
    date_hierarchy = "received_at"
    search_fields = ("from_phone", "text", "wa_message_id", "manager__name")
    ordering = ("-received_at", "-id")
    readonly_fields = ("received_at",)

    def linked_question_link(self, obj):
        if not obj.linked_question_id:
            return "-"
        url = reverse("admin:opscheckin_outboundquestion_change", args=[obj.linked_question_id])
        q = obj.linked_question
        return format_html('<a href="{}">{} • {}</a>', url, q.step, q.status)
    linked_question_link.short_description = "Pergunta"

    def short_text(self, obj):
        t = (obj.text or "").strip()
        return (t[:120] + "…") if len(t) > 120 else t
    short_text.short_description = "Texto"