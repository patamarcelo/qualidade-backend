# opscheckin/models.py
from django.db import models
from django.utils import timezone


class Manager(models.Model):
    name = models.CharField(max_length=80)
    phone_e164 = models.CharField(max_length=20, unique=True)  # ex: 5551999999999
    is_active = models.BooleanField(default=True)

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