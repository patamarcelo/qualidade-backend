# opscheckin/models.py
import re
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


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
    notification_types = models.ManyToManyField(
        "NotificationType",
        through="ManagerNotificationSubscription",
        blank=True,
        related_name="managers",
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
        max_length=24,
        default="text",
        choices=[
            ("agenda", "Agenda"),
            ("reminder", "Reminder"),
            ("manual", "Manual"),
            ("other", "Other"),
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