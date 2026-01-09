# kmltools/models.py
from django.conf import settings
from django.db import models
import uuid

class BillingProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing",
    )

    firebase_uid = models.CharField(max_length=128, unique=True)

    plan = models.CharField(
        max_length=20,
        choices=[("free", "Free"), ("pro", "Pro")],
        default="free",
    )

    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)

    cancel_at_period_end = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} [{self.plan}]"


class WeeklyUsage(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kml_weekly_usage",
    )
    week = models.CharField(max_length=8, db_index=True)  # YYYYWW (ISO week)
    count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "week")
        
        



class KMLMergeJob(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Success"),
        (STATUS_ERROR, "Error"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kml_merge_jobs")

    # ID do processamento (o que você já retorna pro front)
    request_id = models.CharField(max_length=64, db_index=True)

    plan = models.CharField(max_length=32, default="free", db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_SUCCESS, db_index=True)

    # Parâmetros de merge (para reprodutibilidade)
    tol_m = models.FloatField(default=20.0)
    corridor_width_m = models.FloatField(default=1.0)

    # Entradas
    total_files = models.IntegerField(default=0)
    total_polygons = models.IntegerField(default=0)

    # Saídas / métricas (você já calcula)
    output_polygons = models.IntegerField(null=True, blank=True)
    merged_polygons = models.IntegerField(null=True, blank=True)

    input_area_m2 = models.FloatField(null=True, blank=True)
    input_area_ha = models.FloatField(null=True, blank=True)
    output_area_m2 = models.FloatField(null=True, blank=True)
    output_area_ha = models.FloatField(null=True, blank=True)

    # Storage reference (não salva o arquivo no DB)
    storage_path = models.CharField(max_length=512, blank=True, default="")

    # Extra (opcional) — guarda payload completo de métricas / nomes
    metrics = models.JSONField(blank=True, default=dict)
    input_filenames = models.JSONField(blank=True, default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["request_id"]),
        ]

    def __str__(self):
        return f"KMLMergeJob({self.user_id}, {self.request_id}, {self.status})"
