from django.contrib import admin
from datetime import time
from django.db.models import Count, Q, Case, When, Value, IntegerField, F, TimeField
from django.urls import reverse
from django.utils.html import format_html
from django import forms
import re
from django.http import HttpResponseRedirect
from django.contrib.admin.views.main import ChangeList

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
    ManagerPersonalReminder,
    ManagerPersonalReminderDispatch
)


from django.db.models import OuterRef, Subquery, DateTimeField, CharField
from django.utils.timezone import localtime

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


class ManagerPersonalReminderInline(admin.StackedInline):
    model = ManagerPersonalReminder
    extra = 0
    readonly_fields = ("template_name",)
    fields = (
        "title",
        "is_active",
        "schedule_type",
        "time_of_day",
        "weekday",
        "day_of_month",
        "response_mode",
        "template_name",
        "message_text",
    )
    show_change_link = True

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
    inlines = [ ManagerNotificationSubscriptionInline, ManagerPersonalReminderInline ]
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






class ManagerPersonalReminderAdminForm(forms.ModelForm):

    class Meta:
        model = ManagerPersonalReminder
        fields = (
            "manager",
            "is_active",
            "title",
            "description",
            "message_text",
            "schedule_type",
            "time_of_day",
            "weekday",
            "day_of_month",
            "start_date",
            "end_date",
            "response_mode",
            "allowed_window_minutes",
        )
        widgets = {
            "message_text": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": (
                        "Ex.: Olá! Hoje é dia de revisar os extintores do hangar. "
                        "Confirme aqui assim que concluir a atividade."
                    ),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Descrição interna opcional para controle do RH.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)



        self.fields["manager"].help_text = "Selecione o manager que receberá este aviso."
        self.fields["title"].help_text = "Nome curto do aviso para identificação interna."
        self.fields["message_text"].help_text = (
            "Texto principal do lembrete. Esse conteúdo será inserido no template do WhatsApp."
        )
        self.fields["schedule_type"].help_text = "Escolha se o aviso será diário, semanal ou mensal."
        self.fields["time_of_day"].help_text = "Horário do envio do lembrete."
        self.fields["weekday"].help_text = "Usado apenas quando a periodicidade for semanal."
        self.fields["day_of_month"].help_text = "Usado apenas quando a periodicidade for mensal."
        self.fields["response_mode"].help_text = (
            "Sem resposta = só envia. Texto = espera resposta escrita. "
            "Botão = exige confirmação por botão."
        )
        self.fields["allowed_window_minutes"].help_text = (
            "Janela em minutos para o cron considerar o lembrete elegível."
        )



    def _build_summary(self, *, schedule_type, time_of_day, weekday, day_of_month, response_mode, template_name):
        weekday_labels = {
            "0": "segunda-feira",
            "1": "terça-feira",
            "2": "quarta-feira",
            "3": "quinta-feira",
            "4": "sexta-feira",
            "5": "sábado",
            "6": "domingo",
        }

        if schedule_type == ManagerPersonalReminder.SCHEDULE_DAILY:
            freq = f"Todo dia às {time_of_day or '--:--'}"
        elif schedule_type == ManagerPersonalReminder.SCHEDULE_WEEKLY:
            freq = f"Toda {weekday_labels.get(str(weekday), 'semana')} às {time_of_day or '--:--'}"
        elif schedule_type == ManagerPersonalReminder.SCHEDULE_MONTHLY:
            freq = f"Todo dia {day_of_month or '--'} do mês às {time_of_day or '--:--'}"
        else:
            freq = "Periodicidade não definida"

        if response_mode == ManagerPersonalReminder.RESPONSE_BUTTON:
            retorno = "Exige confirmação por botão"
        elif response_mode == ManagerPersonalReminder.RESPONSE_TEXT:
            retorno = "Espera resposta por texto"
        else:
            retorno = "Não exige resposta"

        return (
            f"Frequência: {freq}\n"
            f"Retorno esperado: {retorno}\n"
            f"Template aplicado automaticamente: {template_name}"
        )

    def clean(self):
        cleaned = super().clean()
        return cleaned
    
    

class ManagerPersonalReminderChangeList(ChangeList):
    def get_ordering(self, request, queryset):
        return [
            "manager__name",  # 1) manager
            "sort_group",     # 2) diário -> semanal -> mensal
            "sort_a",         # 3) regra interna
            "sort_b",         # 4) horário por último
            "title",
        ]
        

@admin.register(ManagerPersonalReminder)
class ManagerPersonalReminderAdmin(admin.ModelAdmin):
    form = ManagerPersonalReminderAdminForm
    sortable_by = ()

    list_display = (
        "id",
        "manager_summary",
        "title",
        "status_badge",
        "frequency_badge",
        "schedule_human",
        "response_mode_badge",
        "template_badge",
        "last_sent_display",
        "last_answered_display",
        "last_status_badge",
        "message_preview",
        "updated_at",
    )
    
    list_filter = (
        "is_active",
        "schedule_type",
        "response_mode",
        "manager__branch",
        "manager__division",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "title",
        "code",
        "message_text",
    )
    autocomplete_fields = ("manager",)

    readonly_fields = (
        "delivery_mode_preview",
        "template_name_preview",
        "template_language_preview",
        "resumo_operacional",
    )

    fieldsets = (
        ("Quem vai receber", {
            "fields": (
                "manager",
                "is_active",
            )
        }),
        ("Identificação do aviso", {
            "fields": (
                "title",
                "description",
                "message_text",
            )
        }),
        ("Quando enviar", {
            "fields": (
                "schedule_type",
                "time_of_day",
                "weekday",
                "day_of_month",
                "start_date",
                "end_date",
                "allowed_window_minutes",
            ),
        }),
        ("Como será a resposta", {
            "fields": (
                "response_mode",
            )
        }),
        ("Configuração automática do WhatsApp", {
            "fields": (
                "delivery_mode_preview",
                "template_name_preview",
                "template_language_preview",
                "resumo_operacional",
            ),
        }),
    )
    class Media:
        css = {
            "all": ("opscheckin/admin_personal_reminder.css",)
        }
        js = ("opscheckin/admin_personal_reminder_form.js",)
    
    def get_changelist(self, request, **kwargs):
        return ManagerPersonalReminderChangeList

    def changelist_view(self, request, extra_context=None):
        if "o" in request.GET:
            q = request.GET.copy()
            q.pop("o", None)
            url = request.path
            if q:
                url = f"{url}?{q.urlencode()}"
            return HttpResponseRedirect(url)
        return super().changelist_view(request, extra_context)

    def get_ordering(self, request):
        return ()

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("manager", "manager__branch")
    
        latest_dispatch = ManagerPersonalReminderDispatch.objects.filter(
                reminder=OuterRef("pk")
            ).order_by("-scheduled_for", "-id")
    
        return qs.annotate(
            sort_group=Case(
                When(schedule_type="daily", then=Value(0)),
                When(schedule_type="weekly", then=Value(1)),
                When(schedule_type="monthly", then=Value(2)),
                default=Value(99),
                output_field=IntegerField(),
            ),
            sort_a=Case(
                When(schedule_type="daily", then=Value(0)),
                When(schedule_type="weekly", then=F("weekday")),
                When(schedule_type="monthly", then=F("day_of_month")),
                default=Value(999),
                output_field=IntegerField(),
            ),
            sort_b=Case(
                When(schedule_type="daily", then=F("time_of_day")),
                When(schedule_type="weekly", then=F("time_of_day")),
                When(schedule_type="monthly", then=F("time_of_day")),
                default=Value(time(23, 59, 59)),
                output_field=TimeField(),
            ),

            last_sent_at=Subquery(
                latest_dispatch.values("sent_at")[:1],
                output_field=DateTimeField(),
            ),
            last_answered_at=Subquery(
                latest_dispatch.values("answered_at")[:1],
                output_field=DateTimeField(),
            ),
            last_dispatch_status=Subquery(
                latest_dispatch.values("status")[:1],
                output_field=CharField(),
            ),
        )
        
    def delivery_mode_preview(self, obj):
        return "Template WhatsApp"

    delivery_mode_preview.short_description = "Modo de envio"


    def template_name_preview(self, obj):
        if not obj:
            return "-"

        if obj.response_mode == ManagerPersonalReminder.RESPONSE_BUTTON:
            return ManagerPersonalReminder.DEFAULT_TEMPLATE_CONFIRM

        return ManagerPersonalReminder.DEFAULT_TEMPLATE_TEXT

    template_name_preview.short_description = "Template aplicado"


    def template_language_preview(self, obj):
        return "pt_BR"

    template_language_preview.short_description = "Idioma"


    def resumo_operacional(self, obj):
        if not obj:
            return "-"

        weekday_labels = {
            0: "segunda-feira",
            1: "terça-feira",
            2: "quarta-feira",
            3: "quinta-feira",
            4: "sexta-feira",
            5: "sábado",
            6: "domingo",
        }

        if obj.schedule_type == obj.SCHEDULE_DAILY:
            freq = f"Todo dia às {obj.time_of_day:%H:%M}" if obj.time_of_day else "Todo dia"
        elif obj.schedule_type == obj.SCHEDULE_WEEKLY:
            day = weekday_labels.get(obj.weekday, "-")
            freq = f"Toda {day} às {obj.time_of_day:%H:%M}" if obj.time_of_day else f"Toda {day}"
        elif obj.schedule_type == obj.SCHEDULE_MONTHLY:
            freq = f"Todo dia {obj.day_of_month} do mês às {obj.time_of_day:%H:%M}" if obj.time_of_day else f"Todo dia {obj.day_of_month} do mês"
        else:
            freq = "-"

        if obj.response_mode == obj.RESPONSE_BUTTON:
            retorno = "Exige confirmação por botão"
            template = obj.DEFAULT_TEMPLATE_CONFIRM
        elif obj.response_mode == obj.RESPONSE_TEXT:
            retorno = "Espera resposta por texto"
            template = obj.DEFAULT_TEMPLATE_TEXT
        else:
            retorno = "Não exige resposta"
            template = obj.DEFAULT_TEMPLATE_TEXT

        return (
            f"Frequência: {freq}\n"
            f"Retorno esperado: {retorno}\n"
            f"Template aplicado automaticamente: {template}"
        )

    resumo_operacional.short_description = "Resumo do envio"

    def last_sent_display(self, obj):
        if not getattr(obj, "last_sent_at", None):
            return "-"
        dt = localtime(obj.last_sent_at)
        return dt.strftime("%d/%m/%Y %H:%M")
    last_sent_display.short_description = "Últ. disparo"


    def last_answered_display(self, obj):
        if not getattr(obj, "last_answered_at", None):
            return "-"
        dt = localtime(obj.last_answered_at)
        return dt.strftime("%d/%m/%Y %H:%M")
    last_answered_display.short_description = "Últ. resposta"


    def last_status_badge(self, obj):
        status = getattr(obj, "last_dispatch_status", "") or ""

        styles = {
            "pending": ("#fef3c7", "#92400e", "Pendente"),
            "sent": ("#dbeafe", "#1d4ed8", "Enviado"),
            "answered": ("#dcfce7", "#166534", "Respondido"),
            "missed": ("#fee2e2", "#991b1b", "Expirado"),
            "failed": ("#e5e7eb", "#475569", "Falhou"),
        }

        bg, fg, label = styles.get(status, ("#e5e7eb", "#475569", "-"))

        return format_html(
            '<span style="display:inline-block;padding:5px 10px;'
            'border-radius:999px;background:{};color:{};'
            'font-weight:800;font-size:11px;">{}</span>',
            bg, fg, label,
        )
    last_status_badge.short_description = "Últ. status"
    
    
    def frequency_badge(self, obj):
        if obj.schedule_type == obj.SCHEDULE_DAILY:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#dbeafe;color:#1d4ed8;'
                'font-weight:800;font-size:11px;">Diário</span>'
            )
        if obj.schedule_type == obj.SCHEDULE_WEEKLY:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#ecfccb;color:#3f6212;'
                'font-weight:800;font-size:11px;">Semanal</span>'
            )
        if obj.schedule_type == obj.SCHEDULE_MONTHLY:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#fef3c7;color:#92400e;'
                'font-weight:800;font-size:11px;">Mensal</span>'
            )
        return format_html(
            '<span style="display:inline-block;padding:5px 10px;'
            'border-radius:999px;background:#e5e7eb;color:#475569;'
            'font-weight:800;font-size:11px;">-</span>'
        )
    frequency_badge.short_description = "Frequência"
    

    def manager_summary(self, obj):
        phone = format_phone_br(obj.manager.phone_e164) if obj.manager else "-"
        branch = obj.manager.branch.name if obj.manager and obj.manager.branch else "Sem filial"
        return format_html(
            '<div style="line-height:1.35;">'
            '<div style="font-weight:800;color:#0f172a;">{}</div>'
            '<div style="font-size:12px;color:#64748b;">{} · {}</div>'
            '</div>',
            obj.manager.name if obj.manager else "-",
            phone,
            branch,
        )
    manager_summary.short_description = "Manager"
    

    def status_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#dcfce7;color:#166534;'
                'font-weight:800;font-size:11px;">Ativo</span>'
            )
        return format_html(
            '<span style="display:inline-block;padding:5px 10px;'
            'border-radius:999px;background:#e5e7eb;color:#6b7280;'
            'font-weight:800;font-size:11px;">Inativo</span>'
        )
    status_badge.short_description = "Status"
    

    def schedule_human(self, obj):
        weekday_labels = {
            0: "Segunda",
            1: "Terça",
            2: "Quarta",
            3: "Quinta",
            4: "Sexta",
            5: "Sábado",
            6: "Domingo",
        }

        if obj.schedule_type == obj.SCHEDULE_DAILY:
            text = f"Todo dia às {obj.time_of_day:%H:%M}"
        elif obj.schedule_type == obj.SCHEDULE_WEEKLY:
            text = f"{weekday_labels.get(obj.weekday, '-')} às {obj.time_of_day:%H:%M}"
        elif obj.schedule_type == obj.SCHEDULE_MONTHLY:
            text = f"Dia {obj.day_of_month} às {obj.time_of_day:%H:%M}"
        else:
            text = "-"

        return format_html(
            '<div style="font-weight:700;color:#0f172a;">{}</div>',
            text,
        )
    schedule_human.short_description = "Quando envia"

    def response_mode_badge(self, obj):
        if obj.response_mode == obj.RESPONSE_BUTTON:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#dbeafe;color:#1d4ed8;'
                'font-weight:800;font-size:11px;">Botão</span>'
            )
        if obj.response_mode == obj.RESPONSE_TEXT:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#fef3c7;color:#92400e;'
                'font-weight:800;font-size:11px;">Texto</span>'
            )
        return format_html(
            '<span style="display:inline-block;padding:5px 10px;'
            'border-radius:999px;background:#e5e7eb;color:#475569;'
            'font-weight:800;font-size:11px;">Sem resposta</span>'
        )
    response_mode_badge.short_description = "Retorno"

    def template_badge(self, obj):
        template_name = obj.get_effective_template_name()
        if template_name == obj.DEFAULT_TEMPLATE_CONFIRM:
            return format_html(
                '<span style="display:inline-block;padding:5px 10px;'
                'border-radius:999px;background:#ede9fe;color:#6d28d9;'
                'font-weight:800;font-size:11px;">Confirmação</span>'
            )
        return format_html(
            '<span style="display:inline-block;padding:5px 10px;'
            'border-radius:999px;background:#e0f2fe;color:#0369a1;'
            'font-weight:800;font-size:11px;">Aviso simples</span>'
        )
    template_badge.short_description = "Template"

    def message_preview(self, obj):
        t = (obj.message_text or "").strip()
        if not t:
            return "-"
        short = (t[:90] + "…") if len(t) > 90 else t
        return format_html(
            '<span style="color:#475569;">{}</span>',
            short,
        )
    message_preview.short_description = "Mensagem"

    def save_model(self, request, obj, form, change):
        obj.delivery_mode = ManagerPersonalReminder.DELIVERY_TEMPLATE
        obj.template_language = "pt_BR"
        obj.template_name = obj.get_effective_template_name()

        schedule_type = form.cleaned_data.get("schedule_type")

        if schedule_type != ManagerPersonalReminder.SCHEDULE_WEEKLY:
            obj.weekday = None

        if schedule_type != ManagerPersonalReminder.SCHEDULE_MONTHLY:
            obj.day_of_month = None

        super().save_model(request, obj, form, change)

@admin.register(ManagerPersonalReminderDispatch)
class ManagerPersonalReminderDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "manager",
        "reminder",
        "reference_date",
        "scheduled_for",
        "sent_at",
        "status",
        "answered_at",
        "answer_source",
        "short_answer",
    )
    list_filter = (
        "status",
        "answer_source",
        "reference_date",
        "manager__branch",
        "manager__division",
    )
    search_fields = (
        "manager__name",
        "manager__phone_e164",
        "reminder__title",
        "provider_message_id",
        "answer_text",
    )
    readonly_fields = (
        "reminder",
        "manager",
        "reference_date",
        "scheduled_for",
        "sent_at",
        "provider_message_id",
        "status",
        "answered_at",
        "answer_text",
        "answer_source",
        "inbound_message",
        "outbound_message",
        "raw_response_payload",
        "created_at",
    )

    def short_answer(self, obj):
        t = (obj.answer_text or "").strip()
        return (t[:100] + "…") if len(t) > 100 else (t or "-")
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