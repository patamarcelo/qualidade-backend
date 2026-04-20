from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html
from django import forms
import re

from .models import (
    Branch,
    DailyCheckin,
    DailyManagerEvent,
    DailyManagerEventDispatch,
    Division,
    InboundMessage,
    Manager,
    ManagerNotificationSubscription,
    NotificationType,
    OutboundMessage,
    OutboundQuestion,
)


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


def format_phone_br(phone: str) -> str:
    s = only_digits(phone)

    if not s:
        return "-"

    if s.startswith("55") and len(s) > 10:
        s = s[2:]

    if len(s) < 10:
        return phone or "-"

    ddd = s[:2]
    number = s[2:]

    if len(number) == 8:
        return f"({ddd}) {number[:4]}-{number[4:]}"

    if len(number) == 9:
        return f"({ddd}) {number[:5]}-{number[5:]}"

    return f"({ddd}) {number}"


def pill_badge(text: str, *, bg="#E8F0FE", fg="#1A73E8") -> str:
    return (
        f'<span style="display:inline-block;'
        f'margin:2px 6px 2px 0;'
        f'padding:4px 10px;'
        f'border-radius:999px;'
        f'background:{bg};'
        f'color:{fg};'
        f'font-size:12px;'
        f'font-weight:600;'
        f'line-height:1.4;'
        f'white-space:nowrap;">'
        f'{text}'
        f'</span>'
    )


def notif_badge(text: str, active: bool = True) -> str:
    bg = "#dcfce7" if active else "#e5e7eb"
    fg = "#166534" if active else "#6b7280"
    return (
        f'<span style="display:inline-block;padding:3px 8px;margin:2px;'
        f'border-radius:999px;background:{bg};color:{fg};font-weight:700;'
        f'font-size:11px;">{text}</span>'
    )


class ManagerAdminForm(forms.ModelForm):
    country = forms.CharField(initial="55", required=False, disabled=True, label="DDI")
    ddd = forms.ChoiceField(choices=[(d, d) for d in BR_DDDS], label="DDD", required=True)
    number = forms.CharField(
        label="Número",
        required=True,
        help_text="Informe 8 ou 9 dígitos. Não incluir o DDI.",
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
        fields = (
            "name",
            "country",
            "ddd",
            "number",
            "branch",
            "division",
            "is_active",
            "is_active_resume_agenda",
            "is_active_for_meetings",
            "id_responsavel_farmbox",
            "projeto",
        )

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

        self.instance.phone_e164 = f"55{ddd}{number}"
        return cleaned


class ManagerNotificationSubscriptionInline(admin.StackedInline):
    model = ManagerNotificationSubscription
    extra = 1
    autocomplete_fields = ("notification_type",)
    fields = ("notification_type", "is_active", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "is_active", "managers_count")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            managers_total=Count("managers", distinct=True)
        )

    def managers_count(self, obj):
        return getattr(obj, "managers_total", 0)

    managers_count.short_description = "Qtd. managers"


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "is_active", "managers_count")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            managers_total=Count("managers", distinct=True)
        )

    def managers_count(self, obj):
        return getattr(obj, "managers_total", 0)

    managers_count.short_description = "Qtd. managers"


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    form = ManagerAdminForm
    list_display = (
        "id",
        "name",
        "id_responsavel_farmbox",
        "phone_display",
        "branch_display",
        "divisions_badges",
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
        "branch",
        "division",
        "projeto",
        "notification_subscriptions__is_active",
        "notification_subscriptions__notification_type",
    )
    search_fields = (
        "name",
        "phone_e164",
        "id_responsavel_farmbox",
        "branch__name",
        "division__name",
        "division__code",
        "projeto__nome",
        "notification_subscriptions__notification_type__code",
        "notification_subscriptions__notification_type__name",
    )
    ordering = ("name",)
    inlines = [ManagerNotificationSubscriptionInline]
    filter_horizontal = ("projeto", "division")

    class Media:
        js = ("opscheckin/admin_phone_mask.js",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("branch").prefetch_related(
            "division",
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

    def branch_display(self, obj):
        return obj.branch.name if obj.branch else "-"

    branch_display.short_description = "Filial"
    branch_display.admin_order_field = "branch__name"

    def divisions_badges(self, obj):
        divisions = obj.division.all().order_by("name")
        if not divisions:
            return "-"
        return format_html(
            "".join(
                pill_badge(d.name, bg="#EEF2FF", fg="#4338CA")
                for d in divisions
            )
        )

    divisions_badges.short_description = "Divisões"

    def projetos_badges(self, obj):
        projetos = obj.projeto.all().order_by("nome")
        if not projetos:
            return "-"

        return format_html(
            "".join(
                pill_badge(
                    p.nome.replace("Projeto", "").strip(),
                    bg="#E8F0FE",
                    fg="#1A73E8",
                )
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
        "manager_branch",
        "manager_divisions",
        "notification_type",
        "notification_code",
        "is_active",
        "created_at",
    )
    list_filter = (
        "is_active",
        "notification_type",
        "manager__is_active",
        "manager__is_active_resume_agenda",
        "manager__is_active_for_meetings",
        "manager__branch",
        "manager__division",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "manager__branch__name",
        "manager__division__name",
        "notification_type__code",
        "notification_type__name",
    )
    ordering = ("manager__name", "notification_type__code")
    autocomplete_fields = ("manager", "notification_type")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("manager", "manager__branch", "notification_type")
            .prefetch_related("manager__division")
        )

    def manager_phone(self, obj):
        return format_phone_br(obj.manager.phone_e164)

    manager_phone.short_description = "Telefone"

    def manager_branch(self, obj):
        return obj.manager.branch.name if obj.manager and obj.manager.branch else "-"

    manager_branch.short_description = "Filial"

    def manager_divisions(self, obj):
        divisions = obj.manager.division.all().order_by("name")
        if not divisions:
            return "-"
        return format_html(
            "".join(pill_badge(d.name, bg="#EEF2FF", fg="#4338CA") for d in divisions)
        )

    manager_divisions.short_description = "Divisões"

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
        "manager_branch",
        "date",
        "created_at",
        "day_status",
        "questions_count",
        "pending_sent_count",
        "answered_count",
        "missed_count",
        "inbound_count",
    )
    list_filter = (
        "date",
        "manager",
        "manager__is_active",
        "manager__branch",
        "manager__division",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "manager__branch__name",
        "manager__division__name",
    )
    date_hierarchy = "date"
    ordering = ("-date", "-id")
    inlines = [OutboundQuestionInline, InboundMessageInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("manager", "manager__branch")
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

    def manager_branch(self, obj):
        return obj.manager.branch.name if obj.manager and obj.manager.branch else "-"

    manager_branch.short_description = "Filial"

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
    list_filter = (
        "status",
        "step",
        "checkin__date",
        "checkin__manager__branch",
        "checkin__manager__division",
    )
    search_fields = (
        "checkin__manager__name",
        "checkin__manager__phone_e164",
        "checkin__manager__branch__name",
        "checkin__manager__division__name",
        "answer_text",
    )
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


@admin.register(OutboundMessage)
class OutboundMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sent_at",
        "manager",
        "manager_branch",
        "kind",
        "to_phone",
        "provider_message_id",
        "wa_status",
        "short_text",
    )
    list_filter = (
        "kind",
        "wa_status",
        "sent_at",
        "manager__branch",
        "manager__division",
    )
    date_hierarchy = "sent_at"
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "to_phone",
        "provider_message_id",
        "text",
    )
    ordering = ("-sent_at", "-id")
    readonly_fields = (
        "manager",
        "checkin",
        "related_question",
        "to_phone",
        "provider_message_id",
        "kind",
        "text",
        "sent_at",
        "raw_response",
        "wa_status",
        "wa_sent_at",
        "wa_delivered_at",
        "wa_read_at",
        "wa_last_status_payload",
    )

    def has_add_permission(self, request):
        return False

    def manager_branch(self, obj):
        return obj.manager.branch.name if obj.manager and obj.manager.branch else "-"

    manager_branch.short_description = "Filial"

    def short_text(self, obj):
        t = (obj.text or "").strip()
        return (t[:120] + "…") if len(t) > 120 else t

    short_text.short_description = "Texto"


@admin.register(InboundMessage)
class InboundMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "received_at",
        "manager",
        "manager_branch",
        "from_phone",
        "msg_type",
        "linked_question_link",
        "short_text",
        "processed",
    )
    list_filter = (
        "processed",
        "msg_type",
        "manager",
        "manager__branch",
        "manager__division",
    )
    date_hierarchy = "received_at"
    search_fields = (
        "from_phone",
        "text",
        "wa_message_id",
        "manager__name",
        "manager__branch__name",
        "manager__division__name",
    )
    ordering = ("-received_at", "-id")
    readonly_fields = ("received_at",)

    def manager_branch(self, obj):
        return obj.manager.branch.name if obj.manager and obj.manager.branch else "-"

    manager_branch.short_description = "Filial"

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
        "applies_to_all",
        "target_divisions_summary",
        "target_branches_summary",
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
        "applies_to_all",
        "template_enabled",
        "target_divisions",
        "target_branches",
    )
    search_fields = (
        "name",
        "code",
        "template_name",
        "meet_link",
        "target_divisions__name",
        "target_branches__name",
    )
    readonly_fields = (
        "updated_at",
        "last_reset_at",
    )
    filter_horizontal = (
        "target_divisions",
        "target_branches",
    )

    fieldsets = (
        ("Identificação", {
            "fields": (
                "code",
                "name",
                "is_active",
                "skip_meeting_on",
            )
        }),
        ("Segmentação", {
            "fields": (
                "applies_to_all",
                "target_divisions",
                "target_branches",
            ),
            "description": (
                "Se 'Aplica para todos' estiver ativo, os filtros de divisão e filial são ignorados."
            ),
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

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "target_divisions",
            "target_branches",
        )

    def target_divisions_summary(self, obj):
        items = obj.target_divisions.all().order_by("name")
        if not items:
            return "Todas" if obj.applies_to_all else "-"
        return format_html(
            "".join(pill_badge(x.name, bg="#EEF2FF", fg="#4338CA") for x in items)
        )

    target_divisions_summary.short_description = "Divisões"

    def target_branches_summary(self, obj):
        items = obj.target_branches.all().order_by("name")
        if not items:
            return "Todas" if obj.applies_to_all else "-"
        return format_html(
            "".join(pill_badge(x.name, bg="#ECFDF5", fg="#047857") for x in items)
        )

    target_branches_summary.short_description = "Filiais"


@admin.register(DailyManagerEventDispatch)
class DailyManagerEventDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "manager",
        "manager_branch",
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
        "manager__branch",
        "manager__division",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "manager__branch__name",
        "manager__division__name",
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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "event",
            "manager",
            "manager__branch",
        ).prefetch_related("manager__division")

    def manager_branch(self, obj):
        return obj.manager.branch.name if obj.manager and obj.manager.branch else "-"

    manager_branch.short_description = "Filial"

    def has_add_permission(self, request):
        return False