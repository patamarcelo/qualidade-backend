from django.db import models

# Create your models here.
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

    def __str__(self):
        return f"{self.manager.name} - {self.date}"


class OutboundQuestion(models.Model):
    """
    Representa uma PERGUNTA enviada (pendente ou respondida).
    """

    checkin = models.ForeignKey(
        DailyCheckin, on_delete=models.CASCADE, related_name="questions"
    )
    step = models.CharField(
        max_length=32, db_index=True
    )  # ex: AGENDA, STARTED, NOW, BLOCKERS...
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

    def __str__(self):
        return f"{self.checkin} - {self.step} - {self.status}"
