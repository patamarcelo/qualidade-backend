from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html
from django import forms
import re

from .models import (
    Manager,
    DailyCheckin,
    OutboundQuestion,
    InboundMessage,
    NotificationType,
    ManagerNotificationSubscription,
    DailyManagerEvent,
    DailyManagerEventDispatch,
)


def format_phone_br(phone: str) -> str:
    s = only_digits(phone)

    if not s:
        return "-"

    # se vier com 55 salvo por algum motivo, remove só para exibição
    if s.startswith("55") and len(s) > 10:
        s = s[2:]

    if len(s) < 10:
        return phone or "-"

    ddd = s[:2]
    number = s[2:]

    # formato esperado do projeto: 8 dígitos
    if len(number) == 8:
        return f"({ddd}) {number[:4]}-{number[4:]}"

    # fallback caso exista algum legado com 9 dígitos
    if len(number) == 9:
        return f"({ddd}) {number[:5]}-{number[5:]}"

    return f"({ddd}) {number}"


# opscheckin/admin.py
BR_DDDS = [
    "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "21", "22", "24", "27", "28",
    "31", "32", "33", "34", "35", "37", "38",
    "41", "42", "43", "44", "45", "46",
    "47", "48", "49",
    "51", "53", "54", "55",
    "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "71", "73", "74", "75", "77", "79",
    "81", "82", "83", "84", "85", "86", "87", "88", "89",
    "91", "92", "93", "94", "95", "96", "97", "98", "99",
]


def only_digits(v: str) -> str:
    return re.sub(r"\D+", "", str(v or ""))


def notif_badge(code: str, active: bool = True) -> str:
    bg = "#dcfce7" if active else "#e5e7eb"
    fg = "#166534" if active else "#6b7280"
    return (
        f'<span style="display:inline-block;padding:3px 8px;margin:2px;'
        f'border-radius:999px;background:{bg};color:{fg};font-weight:700;'
        f'font-size:11px;">{code}</span>'
    )


class ManagerAdminForm(forms.ModelForm):
    country = forms.CharField(initial="55", required=False, disabled=True, label="DDI")
    ddd = forms.ChoiceField(choices=[(d, d) for d in BR_DDDS], label="DDD", required=True)
    number = forms.CharField(
        label="Número",
        required=True,
        help_text="Informe no máximo 8 dígitos neste campo. Não incluir o 9º Dígito",
        widget=forms.TextInput(
            attrs={
                "placeholder": "91234-5678",
                "maxlength": "9",
                "inputmode": "numeric",
            }
        ),
    )

    class Meta:
        model = Manager
        fields = ("name", "country", "ddd", "number", "is_active", "is_active_resume_agenda", 'is_active_for_meetings', "id_responsavel_farmbox","projeto",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.phone_e164:
            s = only_digits(self.instance.phone_e164)
            if s.startswith("55") and len(s) >= 4:
                self.fields["ddd"].initial = s[2:4]
                self.fields["number"].initial = s[4:]

    def clean(self):
        cleaned = super().clean()

        ddd = cleaned.get("ddd")
        number_raw = cleaned.get("number")
        number = only_digits(number_raw)

        if not ddd:
            return cleaned

        if len(number) not in (8, 9):
            self.add_error("number", "Número deve ter 8 (fixo) ou 9 (celular) dígitos.")
            return cleaned

        phone_e164 = f"55{ddd}{number}"
        self.instance.phone_e164 = phone_e164
        return cleaned
    
    

class ManagerNotificationSubscriptionInline(admin.StackedInline):
    model = ManagerNotificationSubscription
    extra = 1
    autocomplete_fields = ("notification_type",)
    fields = ("notification_type", "is_active", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    form = ManagerAdminForm
    list_display = (
        "id",
        "name",
        "id_responsavel_farmbox",
        "phone_display",
        "projetos_badges",
        "is_active",
        "is_active_resume_agenda",
        "is_active_for_meetings",
        "notification_codes",
        "notifications_count",
        "last_checkin_link",
    )
    list_filter = (
        "is_active",
        "is_active_resume_agenda",
        "is_active_for_meetings",
        "projeto",
        "notification_subscriptions__is_active",
        "notification_subscriptions__notification_type",
    )
    search_fields = (
        "name",
        "phone_e164",
        "id_responsavel_farmbox",
        "projeto__nome",  # ajuste se o campo do Projeto tiver outro nome
        "notification_subscriptions__notification_type__code",
        "notification_subscriptions__notification_type__name",
    )
    ordering = ("name",)
    inlines = [ManagerNotificationSubscriptionInline]
    filter_horizontal = ("projeto",)

    class Media:
        js = ("opscheckin/admin_phone_mask.js",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related(
            "projeto",
            "notification_subscriptions__notification_type",
            "checkins",
        ).annotate(
            notifications_total=Count(
                "notification_subscriptions",
                filter=Q(notification_subscriptions__is_active=True),
                distinct=True,
            )
        )
        return qs

    def phone_display(self, obj):
        return format_phone_br(obj.phone_e164)

    phone_display.short_description = "Telefone"
    phone_display.admin_order_field = "phone_e164"

    def projetos_badges(self, obj):
        projetos = obj.projeto.all().order_by("nome")  # ajuste se não for "nome"
        if not projetos:
            return "-"

        return format_html(
            "".join(
                (
                    '<span style="'
                    'display:inline-block;'
                    'margin:2px 6px 2px 0;'
                    'padding:4px 10px;'
                    'border-radius:999px;'
                    'background:#E8F0FE;'
                    'color:#1A73E8;'
                    'font-size:12px;'
                    'font-weight:600;'
                    'line-height:1.4;'
                    'white-space:nowrap;'
                    '">'
                    "{}"
                    "</span>"
                ).format(p.nome.replace('Projeto', '').strip())  # ajuste se não for "nome"
                for p in projetos
            )
        )

    projetos_badges.short_description = "Projetos"

    def notification_codes(self, obj):
        subs = obj.notification_subscriptions.select_related("notification_type").order_by(
            "notification_type__code"
        )
        if not subs:
            return "-"
        return format_html(
            "".join(
                notif_badge(s.notification_type.name, s.is_active)
                for s in subs
            )
        )

    notification_codes.short_description = "Notificações"

    def notifications_count(self, obj):
        return getattr(
            obj,
            "notifications_total",
            obj.notification_subscriptions.filter(is_active=True).count(),
        )

    notifications_count.short_description = "Qtd. notif."

    def last_checkin_link(self, obj):
        last = obj.checkins.order_by("-date", "-id").first()
        if not last:
            return "-"
        url = reverse("admin:opscheckin_dailycheckin_change", args=[last.id])
        return format_html(
            '<a href="{}">{} ({})</a>',
            url,
            last.date,
            last.questions.count(),
        )

    last_checkin_link.short_description = "Último check-in"

@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "name",
        "is_active",
        "subscriptions_count",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    ordering = ("code",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            subscriptions_total=Count(
                "subscriptions",
                filter=Q(subscriptions__is_active=True),
                distinct=True,
            )
        )
        return qs

    def subscriptions_count(self, obj):
        return getattr(obj, "subscriptions_total", obj.subscriptions.filter(is_active=True).count())

    subscriptions_count.short_description = "Managers ativos"


@admin.register(ManagerNotificationSubscription)
class ManagerNotificationSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "manager",
        "manager_phone",
        "notification_type",
        "notification_code",
        "is_active",
        "created_at",
    )
    list_filter = (
        "is_active",
        "notification_type",
        "manager__is_active",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "notification_type__code",
        "notification_type__name",
    )
    ordering = ("manager__name", "notification_type__code")
    autocomplete_fields = ("manager", "notification_type")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("manager", "notification_type")

    def manager_phone(self, obj):
        return format_phone_br(obj.manager.phone_e164)



    manager_phone.short_description = "Telefone"

    def notification_code(self, obj):
        return obj.notification_type.code

    notification_code.short_description = "Code"


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
    readonly_fields = (
        "received_at",
        "from_phone",
        "wa_message_id",
        "msg_type",
        "text",
        "linked_question_link",
        "processed",
    )
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
                filter=Q(
                    questions__status="pending",
                    questions__sent_at__isnull=False,
                    questions__answered_at__isnull=True,
                ),
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
        return getattr(
            obj,
            "pending_sent_total",
            obj.questions.filter(status="pending", sent_at__isnull=False, answered_at__isnull=True).count(),
        )

    pending_sent_count.short_description = "Pendentes (enviadas)"

    def day_status(self, obj):
        pending_sent = getattr(obj, "pending_sent_total", None)
        missed = getattr(obj, "missed_total", None)

        if pending_sent is None:
            pending_sent = obj.questions.filter(
                status="pending",
                sent_at__isnull=False,
                answered_at__isnull=True,
            ).count()

        if missed is None:
            missed = obj.questions.filter(status="missed").count()

        if pending_sent > 0:
            return format_html('<span style="color:#f59e0b;font-weight:700;">Em aberto</span>')
        if missed > 0:
            return format_html('<span style="color:#ef4444;font-weight:700;">Missed</span>')
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

@admin.register(DailyManagerEvent)
class DailyManagerEventAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "is_active",
        "default_time",
        "override_date",
        "override_time",
        "skip_meeting_on",
        "reminder_offset_minutes",
        "allowed_window_minutes",
        "template_enabled",
        "template_name",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "template_enabled",
    )
    search_fields = (
        "name",
        "code",
        "template_name",
        "meet_link",
    )
    readonly_fields = (
        "updated_at",
        "last_reset_at",
    )

    fieldsets = (
        ("Identificação", {
            "fields": (
                "code",
                "name",
                "is_active",
                "skip_meeting_on"
            )
        }),
        ("Horários", {
            "fields": (
                "default_time",
                "override_date",
                "override_time",
                "reminder_offset_minutes",
                "allowed_window_minutes",
            )
        }),
        ("Mensagem / template", {
            "fields": (
                "template_enabled",
                "template_name",
                "template_language",
                "meet_link",
            )
        }),
        ("Controle interno", {
            "fields": (
                "last_reset_at",
                "updated_at",
            )
        }),
    )


@admin.register(DailyManagerEventDispatch)
class DailyManagerEventDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "manager",
        "event_date",
        "scheduled_event_time",
        "target_send_time",
        "sent_at",
        "status",
        "provider_message_id",
    )
    list_filter = (
        "event",
        "status",
        "event_date",
        "scheduled_event_time",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "event__name",
        "event__code",
        "provider_message_id",
    )
    readonly_fields = (
        "event",
        "manager",
        "event_date",
        "scheduled_event_time",
        "target_send_time",
        "sent_at",
        "provider_message_id",
        "status",
    )

    def has_add_permission(self, request):
        return False
    
    
