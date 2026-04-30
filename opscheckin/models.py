# opscheckin/models.py
import re
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from diamante.models import Projeto

from django.conf import settings

def only_digits(v: str) -> str:
    return re.sub(r"\D+", "", str(v or ""))

class NotificationType(models.Model):
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Tipo de notificação"
        verbose_name_plural = "Tipos de notificação"

    def __str__(self):
        return f"{self.name} - {self.code}"
    

class Division(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Divisão"
        verbose_name_plural = "Divisões"

    def __str__(self):
        return self.name


class Branch(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Filial"
        verbose_name_plural = "Filiais"

    def __str__(self):
        return self.name


class ManagerNotificationSubscription(models.Model):
    manager = models.ForeignKey(
        "Manager",
        on_delete=models.CASCADE,
        related_name="notification_subscriptions",
    )
    notification_type = models.ForeignKey(
        "NotificationType",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("manager", "notification_type")]
        indexes = [
            models.Index(fields=["manager", "is_active"]),
            models.Index(fields=["notification_type", "is_active"]),
        ]
        verbose_name = "Assinatura de notificação"
        verbose_name_plural = "Assinaturas de notificações"

    def __str__(self):
        return f"{self.manager.name} -> {self.notification_type.code}"




class Manager(models.Model):
    name = models.CharField(max_length=80)
    phone_e164 = models.CharField(max_length=12, unique=True)  # ex: 5551999999999
    
    is_active = models.BooleanField(
        default=True,
        help_text="Participa do fluxo de agenda diária"
    )
    
    is_active_resume_agenda = models.BooleanField(
        default=False,
        help_text="Recebe o resumo consolidado da agenda (diretoria)"
    )
    
    is_active_for_meetings = models.BooleanField(
        default=False,
        help_text="Recebe lembretes de reuniões diárias"
    )
    
    notification_types = models.ManyToManyField(
        "NotificationType",
        through="ManagerNotificationSubscription",
        blank=True,
        related_name="managers",
    )
    
    division = models.ManyToManyField(
        "Division",
        blank=True,
        related_name="managers",
        verbose_name="Divisões",
    )

    branch = models.ForeignKey(
        "Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managers",
        verbose_name="Filial",
    )
    
    
    id_responsavel_farmbox = models.IntegerField("ID FarmBox",  blank=True, null=True, unique=True)
    projeto = models.ManyToManyField(Projeto, blank=True, default=None, related_name="projeto_manager")
    
    
    personal_reminder_managers = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="personal_reminder_coordinators",
        verbose_name="Managers sob coordenação",
        help_text="Managers/funcionários cujos avisos pessoais serão acompanhados por este coordenador.",
    )

    is_personal_reminder_coordinator = models.BooleanField(
        default=False,
        verbose_name="Coordenador de avisos pessoais",
        help_text="Recebe confirmações e resumo diário dos avisos pessoais dos managers relacionados.",
    )
    
    
    
    
    
    
    
    
    def clean(self):
        super().clean()
        s = only_digits(self.phone_e164)

        # aceita salvar já normalizado
        if s.startswith("55") and len(s) in (12, 13):
            self.phone_e164 = s
            return

        # se alguém tentar salvar sem 55, tenta prefixar (fallback)
        if len(s) in (10, 11):  # DDD + numero
            s = "55" + s

        if not (s.startswith("55") and len(s) in (12, 13)):
            raise ValidationError({"phone_e164": "Telefone inválido. Use DDD + número."})

        self.phone_e164 = s

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.phone_e164})"


class DailyCheckin(models.Model):
    manager = models.ForeignKey(
        Manager, on_delete=models.CASCADE, related_name="checkins"
    )
    date = models.DateField(db_index=True)  # dia local (America/Sao_Paulo)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("manager", "date")]
        indexes = [
            models.Index(fields=["manager", "date"]),
        ]

    def __str__(self):
        return f"{self.manager.name} - {self.date}"


class OutboundQuestion(models.Model):
    """
    Representa uma PERGUNTA enviada (pendente ou respondida).
    """

    checkin = models.ForeignKey(
        DailyCheckin, on_delete=models.CASCADE, related_name="questions"
    )
    step = models.CharField(max_length=32, db_index=True)  # ex: AGENDA, STATUS_08...
    scheduled_for = models.DateTimeField(db_index=True)  # horário-alvo
    sent_at = models.DateTimeField(null=True, blank=True)

    prompt_text = models.TextField(blank=True, default="")
    
    reminder_count = models.PositiveSmallIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)

    answered_at = models.DateTimeField(null=True, blank=True)
    answer_text = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("answered", "Answered"),
            ("missed", "Missed"),
        ],
        db_index=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["checkin", "status", "answered_at"]),
            models.Index(fields=["checkin", "step"]),
        ]

    def __str__(self):
        return f"{self.checkin} - {self.step} - {self.status}"


class OutboundMessage(models.Model):
    """
    Tudo que o sistema ENVIA (log). Isso é o espelho do InboundMessage.
    """
    manager = models.ForeignKey(
        Manager, on_delete=models.SET_NULL, null=True, blank=True, related_name="outbound_messages"
    )
    checkin = models.ForeignKey(
        DailyCheckin, on_delete=models.SET_NULL, null=True, blank=True, related_name="outbound_messages"
    )
    related_question = models.ForeignKey(
        OutboundQuestion, on_delete=models.SET_NULL, null=True, blank=True, related_name="outbound_messages"
    )

    to_phone = models.CharField(max_length=20, db_index=True)  # e164 sem "+"
    provider_message_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    kind = models.CharField(
        max_length=150,
        default="text",
        choices=[
            ("agenda", "Agenda"),
            ("reminder", "Reminder"),
            ("manual", "Manual"),
            ("other", "Other"),
            ("agenda_summary_director", "Resumo diretoria"),
            ("agenda_summary_director_overview", "Resumo diretoria geral"),
            ("agenda_summary_director_actions", "Ações resumo diretoria"),
            ("daily_meeting_reminder", "Lembrete reunião diária"),
            ("daily_meeting_reminder_changed", "Lembrete reunião diária alterada"),
            ("personal_reminder", "Aviso pessoal"),
            ("personal_reminder_coordinator_notice", "Aviso ao coordenador"),
            ("personal_reminder_coordinator_daily_action", "Botão resumo diário avisos"),
            ("personal_reminder_coordinator_daily_summary", "Resumo diário avisos"),
            ("manual_template", "Manual via template"),
        ],
        db_index=True,
    )

    text = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)

    raw_response = models.JSONField(null=True, blank=True)
    
    wa_status = models.CharField(
        max_length=16,
        blank=True,
        default="",
        choices=[
            ("", "Unknown"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
            ("failed", "Failed"),
        ],
        db_index=True,
    )
    wa_sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    wa_delivered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    wa_read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    wa_last_status_payload = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["to_phone", "sent_at"]),
            models.Index(fields=["manager", "sent_at"]),
            models.Index(fields=["checkin", "sent_at"]),
            models.Index(fields=["kind", "sent_at"]),
        ]

    def __str__(self):
        who = self.manager.name if self.manager else self.to_phone
        return f"Outbound {who} @ {self.sent_at:%Y-%m-%d %H:%M} - {self.kind}"
    

class InboundMessage(models.Model):
    """
    Tudo que chega do WhatsApp (sempre gravado).
    Depois a gente associa (ou não) a uma pergunta pendente.
    """

    manager = models.ForeignKey(
        Manager, on_delete=models.SET_NULL, null=True, blank=True, related_name="inbound_messages"
    )

    from_phone = models.CharField(max_length=20, db_index=True)  # e164 sem "+"
    wa_message_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    text = models.TextField(blank=True, default="")
    msg_type = models.CharField(max_length=32, blank=True, default="text")  # text/button/interactive/unknown

    received_at = models.DateTimeField(default=timezone.now, db_index=True)

    # associação opcional
    checkin = models.ForeignKey(
        DailyCheckin, on_delete=models.SET_NULL, null=True, blank=True, related_name="inbound_messages"
    )
    linked_question = models.ForeignKey(
        OutboundQuestion, on_delete=models.SET_NULL, null=True, blank=True, related_name="inbound_messages"
    )

    # controle de processamento futuro (agente)
    processed = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    # debug / auditoria (opcional)
    raw_payload = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["from_phone", "received_at"]),
            models.Index(fields=["manager", "received_at"]),
            models.Index(fields=["processed", "received_at"]),
        ]

    def __str__(self):
        who = self.manager.name if self.manager else self.from_phone
        return f"Inbound {who} @ {self.received_at:%Y-%m-%d %H:%M} - {self.text[:40]}"
    

class AgendaItem(models.Model):
    checkin = models.ForeignKey(DailyCheckin, on_delete=models.CASCADE, related_name="agenda_items")
    idx = models.IntegerField()  # ordem
    text = models.CharField(max_length=280)
    status = models.CharField(max_length=16, default="open", choices=[
        ("open","Open"),
        ("done","Done"),
        ("skip","Skip"),
    ])
    done_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    

class DailyManagerEvent(models.Model):
    EVENT_CHOICES = [
        ("farm_daily_agenda", "Agenda diária da fazenda"),
    ]

    code = models.CharField(max_length=60, choices=EVENT_CHOICES, unique=True)
    name = models.CharField(max_length=120, default="Agenda diária da fazenda")

    is_active = models.BooleanField(default=True)

    default_time = models.TimeField()
    override_date = models.DateField(null=True, blank=True)
    override_time = models.TimeField(null=True, blank=True)

    meet_link = models.URLField(blank=True, default="")

    template_name = models.CharField(max_length=120, blank=True, default="daily_meeting_reminder")
    template_language = models.CharField(max_length=20, default="pt_BR")
    template_enabled = models.BooleanField(default=False)

    reminder_offset_minutes = models.PositiveSmallIntegerField(default=60)
    allowed_window_minutes = models.PositiveSmallIntegerField(default=90)

    last_reset_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    skip_meeting_on = models.DateField(
        "Pular reunião na data",
        null=True,
        blank=True,
        help_text="Se preenchido com a data de hoje, o sistema não envia os lembretes apenas nesse dia.",
        db_index=True,
    )

    applies_to_all = models.BooleanField(
        default=True,
        help_text="Quando ativo, ignora filtros de divisão e filial."
    )

    target_divisions = models.ManyToManyField(
        "Division",
        blank=True,
        related_name="daily_manager_events",
        verbose_name="Divisões alvo",
    )

    target_branches = models.ManyToManyField(
        "Branch",
        blank=True,
        related_name="daily_manager_events",
        verbose_name="Filiais alvo",
    )

    def get_effective_time(self, day):
        if self.override_date == day and self.override_time:
            return self.override_time
        return self.default_time

    def reset_override_if_past(self, day):
        if self.override_date and self.override_date < day:
            self.override_date = None
            self.override_time = None
            self.save(update_fields=["override_date", "override_time"])
            
class DailyManagerEventDispatch(models.Model):
    event = models.ForeignKey(DailyManagerEvent, on_delete=models.CASCADE, related_name="dispatches")
    manager = models.ForeignKey(Manager, on_delete=models.CASCADE, related_name="event_dispatches")

    event_date = models.DateField(db_index=True)
    scheduled_event_time = models.TimeField()
    target_send_time = models.TimeField()

    sent_at = models.DateTimeField(default=timezone.now)
    provider_message_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=20, default="sent")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "event",
                    "manager",
                    "event_date",
                    "scheduled_event_time",
                    "target_send_time",
                ],
                name="uniq_daily_manager_event_dispatch_slot",
            )
        ]
        

class ManagerPersonalReminder(models.Model):
    SCHEDULE_DAILY = "daily"
    SCHEDULE_WEEKLY = "weekly"
    SCHEDULE_MONTHLY = "monthly"

    SCHEDULE_CHOICES = [
        (SCHEDULE_DAILY, "Diário"),
        (SCHEDULE_WEEKLY, "Semanal"),
        (SCHEDULE_MONTHLY, "Mensal"),
    ]

    DELIVERY_TEXT = "text"
    DELIVERY_TEMPLATE = "template"

    DELIVERY_CHOICES = [
        (DELIVERY_TEXT, "Somente texto"),
        (DELIVERY_TEMPLATE, "Template WhatsApp"),
    ]

    RESPONSE_NONE = "none"
    RESPONSE_TEXT = "text"
    RESPONSE_BUTTON = "button"

    RESPONSE_CHOICES = [
        (RESPONSE_NONE, "Sem resposta"),
        (RESPONSE_TEXT, "Resposta por texto"),
        (RESPONSE_BUTTON, "Botão de confirmação"),
    ]
    
    DEFAULT_TEMPLATE_TEXT = "manager_personal_reminder_text"
    DEFAULT_TEMPLATE_CONFIRM = "manager_personal_reminder_confirm"

    manager = models.ForeignKey(
        "Manager",
        on_delete=models.CASCADE,
        related_name="personal_reminders",
        verbose_name="Manager",
    )

    code = models.CharField(max_length=80, blank=True, default="", db_index=True)
    title = models.CharField(max_length=120, verbose_name="Título")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="Descrição interna")

    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    schedule_type = models.CharField(
        max_length=16,
        choices=SCHEDULE_CHOICES,
        default=SCHEDULE_DAILY,
        db_index=True,
        verbose_name="Periodicidade",
    )
    time_of_day = models.TimeField(verbose_name="Horário do envio")

    weekday = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Dia da semana",
        help_text="0=segunda ... 6=domingo. Usado apenas no semanal.",
    )
    day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Dia do mês",
        help_text="Usado apenas no mensal.",
    )

    start_date = models.DateField(null=True, blank=True, verbose_name="Início")
    end_date = models.DateField(null=True, blank=True, verbose_name="Fim")

    delivery_mode = models.CharField(
        max_length=16,
        choices=DELIVERY_CHOICES,
        default=DELIVERY_TEMPLATE,
        verbose_name="Modo de envio",
    )

    response_mode = models.CharField(
        max_length=16,
        choices=RESPONSE_CHOICES,
        default=RESPONSE_NONE,
        verbose_name="Tipo de resposta",
        help_text="Define se o aviso exige botão, texto ou não exige retorno.",
    )

    message_text = models.TextField(blank=True, default="", verbose_name="Mensagem")
    template_name = models.CharField(max_length=120, blank=True, default="", verbose_name="Nome do template")
    template_language = models.CharField(max_length=20, default="pt_BR", verbose_name="Idioma do template")

    allowed_window_minutes = models.PositiveSmallIntegerField(
        default=30,
        verbose_name="Janela de envio (min)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["manager__name", "time_of_day", "title"]
        verbose_name = "Aviso pessoal do manager"
        verbose_name_plural = "Avisos pessoais dos managers"
        indexes = [
            models.Index(fields=["manager", "is_active"]),
            models.Index(fields=["schedule_type", "is_active"]),
            models.Index(fields=["time_of_day", "is_active"]),
        ]

    def get_effective_template_name(self) -> str:
        if self.response_mode == self.RESPONSE_BUTTON:
            return self.DEFAULT_TEMPLATE_CONFIRM
        return self.DEFAULT_TEMPLATE_TEXT
    
    def clean(self):
        super().clean()
        
        if self.response_mode == self.RESPONSE_BUTTON and self.delivery_mode != self.DELIVERY_TEMPLATE:
            raise ValidationError({
                "delivery_mode": "Botão de confirmação exige envio por template."
            })

        if self.delivery_mode == self.DELIVERY_TEMPLATE:
            self.template_name = self.get_effective_template_name()
            

        if self.schedule_type == self.SCHEDULE_WEEKLY and self.weekday is None:
            raise ValidationError({"weekday": "Informe o dia da semana para periodicidade semanal."})

        if self.schedule_type != self.SCHEDULE_WEEKLY:
            self.weekday = None

        if self.schedule_type == self.SCHEDULE_MONTHLY:
            if self.day_of_month is None:
                raise ValidationError({"day_of_month": "Informe o dia do mês para periodicidade mensal."})
            if not 1 <= self.day_of_month <= 31:
                raise ValidationError({"day_of_month": "Use um valor entre 1 e 31."})
        else:
            self.day_of_month = None

        if self.response_mode == self.RESPONSE_BUTTON and self.delivery_mode != self.DELIVERY_TEMPLATE:
            raise ValidationError({
                "delivery_mode": "Botão de confirmação exige envio por template."
            })

        if self.delivery_mode == self.DELIVERY_TEMPLATE and not self.template_name:
            raise ValidationError({"template_name": "Informe o template quando o modo de envio for template."})

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "A data final deve ser maior ou igual à data inicial."})
    
    def save(self, *args, **kwargs):
        if self.delivery_mode == self.DELIVERY_TEMPLATE:
            self.template_name = self.get_effective_template_name()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.manager.name} - {self.title}"
    
class ManagerPersonalReminderDispatch(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_ANSWERED = "answered"
    STATUS_MISSED = "missed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_SENT, "Enviado"),
        (STATUS_ANSWERED, "Respondido"),
        (STATUS_MISSED, "Expirado"),
        (STATUS_FAILED, "Falhou"),
    ]

    ANSWER_NONE = "none"
    ANSWER_TEXT = "text"
    ANSWER_BUTTON = "button"
    ANSWER_MANUAL = "manual"

    ANSWER_SOURCE_CHOICES = [
        (ANSWER_NONE, "Sem resposta"),
        (ANSWER_TEXT, "Texto"),
        (ANSWER_BUTTON, "Botão"),
        (ANSWER_MANUAL, "Manual"),
    ]

    reminder = models.ForeignKey(
        "ManagerPersonalReminder",
        on_delete=models.CASCADE,
        related_name="dispatches",
        verbose_name="Aviso",
    )
    manager = models.ForeignKey(
        "Manager",
        on_delete=models.CASCADE,
        related_name="personal_reminder_dispatches",
        verbose_name="Manager",
    )

    reference_date = models.DateField(db_index=True, verbose_name="Data de referência")
    scheduled_for = models.DateTimeField(db_index=True, verbose_name="Agendado para")

    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    provider_message_id = models.CharField(max_length=128, blank=True, default="", db_index=True)

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    answered_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Respondido em",
    )
    answer_text = models.TextField(blank=True, default="", verbose_name="Resposta")
    answer_source = models.CharField(
        max_length=16,
        choices=ANSWER_SOURCE_CHOICES,
        default=ANSWER_NONE,
        verbose_name="Origem da resposta",
    )

    inbound_message = models.ForeignKey(
        "InboundMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_reminder_dispatches",
    )
    outbound_message = models.ForeignKey(
        "OutboundMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_reminder_dispatches",
    )

    raw_response_payload = models.JSONField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_for", "-id"]
        verbose_name = "Disparo de aviso pessoal"
        verbose_name_plural = "Disparos de avisos pessoais"
        constraints = [
            models.UniqueConstraint(
                fields=["reminder", "manager", "reference_date"],
                name="uniq_manager_personal_reminder_dispatch_day",
            )
        ]
        indexes = [
            models.Index(fields=["manager", "status", "scheduled_for"]),
            models.Index(fields=["reminder", "reference_date"]),
            models.Index(fields=["provider_message_id"]),
        ]

    def __str__(self):
        return f"{self.manager.name} - {self.reminder.title} - {self.reference_date}"
    
class OpsBoardAccess(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ops_board_access",
        verbose_name="Usuário Django",
    )

    coordinator = models.ForeignKey(
        "Manager",
        on_delete=models.CASCADE,
        related_name="board_accesses",
        limit_choices_to={"is_personal_reminder_coordinator": True},
        verbose_name="Coordenador",
        help_text="Coordenador cujo grupo este usuário poderá visualizar no board.",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Ativo",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Acesso ao Board OpsCheckin"
        verbose_name_plural = "Acessos ao Board OpsCheckin"

    def __str__(self):
        return f"{self.user} → {self.coordinator}"