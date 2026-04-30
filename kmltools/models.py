# kmltools/models.py
from django.conf import settings
from django.db import models
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import date


import hashlib
import secrets
class UnlockFeedback(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    anon_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)


    use_case = models.CharField(max_length=100)
    frequency = models.CharField(max_length=50)
    willingness = models.CharField(max_length=50)
    price_expectation = models.CharField(max_length=50)
    
    other_use_case_text = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"UnlockFeedback {self.id}"

class BillingProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing",
    )

    firebase_uid = models.CharField(max_length=128, unique=True)

    plan = models.CharField(
        max_length=20,
        choices=[
            ("free", "Free"),
            ("prepaid", "Prepaid"),
            ("pro_monthly", "Pro Monthly"),
            ("pro_yearly", "Pro Yearly"),
            ("pro", "Pro")
        ],
        default="free",
    )
    
    remove_from_mail_list = models.BooleanField(default=False)

    # Stripe
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)
    cancel_at_period_end = models.BooleanField(default=False)

    # =========================
    # Créditos
    # =========================
    # Free: reseta para 2 todo mês (não cumulativo)
    free_monthly_credits = models.PositiveIntegerField(default=0)
    free_month_key = models.DateField(blank=True, null=True)  # YYYY-MM-01

    # Prepaid: cumulativo, nunca expira
    prepaid_credits = models.PositiveIntegerField(default=0)

    # Auditoria/analytics (total de merges)
    credits_used_total = models.PositiveIntegerField(default=0)
    
    # =========================
    # ICP / Onboarding (quem é o cliente)
    # =========================
    USE_CASE_CHOICES = [
        ("agriculture", "Agriculture / Farm management"),
        ("drone_mapping", "Drone mapping"),
        ("gis", "GIS analysis"),
        ("engineering", "Engineering / Infrastructure"),
        ("real_estate", "Real estate / Land survey"),
        ("academic", "Academic / Study"),
        ("other", "Other"),
    ]

    USAGE_FREQUENCY_CHOICES = [
        ("occasional", "Occasionally"),
        ("weekly", "Weekly"),
        ("daily", "Daily"),
        ("large_batches", "Large batches"),
    ]

    use_case = models.CharField(max_length=32, blank=True, default="", db_index=True)
    usage_frequency = models.CharField(max_length=32, blank=True, default="", db_index=True)

    onboarding_completed_at = models.DateTimeField(blank=True, null=True)
    onboarding_skipped_count = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    free_unlock_used = models.BooleanField(default=False)
    
    country = models.CharField(max_length=2, blank=True, null=True)      # ISO-2 (BR, US, IN)
    country_name = models.CharField(max_length=64, blank=True, null=True)
    country_source = models.CharField(max_length=16, blank=True, null=True)  # "ip"
    country_set_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.email} [{self.plan}]"

    @property
    def is_unlimited(self) -> bool:
        return self.plan in ("pro_monthly", "pro_yearly")

    def _month_key(self, d: date) -> date:
        return date(d.year, d.month, 1)

    def reset_free_monthly_if_needed(self, monthly_amount=2, now=None):
        """
        Free: NÃO cumulativo. Quando muda o mês, reseta para monthly_amount.
        """
        if (self.plan or "").lower() != "free":
            return

        today = now or timezone.localdate()
        mk = self._month_key(today)

        if self.free_month_key == mk:
            return  # nada a fazer

        self.free_month_key = mk
        self.free_monthly_credits = monthly_amount

        # ✅ Se não tem PK, faz INSERT (sem update_fields)
        if not self.pk:
            self.save()
            return

        # ✅ Se já tem PK, faz UPDATE parcial
        self.save(update_fields=["free_month_key", "free_monthly_credits", "updated_at"])

    def consume_one_merge_credit(self, monthly_free_amount=2) -> str:
        """
        Consome 1 crédito por merge, conforme regras:
        - Pro: ilimitado (não consome saldo)
        - Free: reseta mensal para 2 e consome primeiro free; se acabar, usa prepaid
        - Prepaid: consome prepaid
        Retorna qual bucket foi usado: 'pro'|'free'|'prepaid'
        Lança ValueError('INSUFFICIENT_CREDITS') se não houver saldo.
        """
        if self.is_unlimited:
            self.credits_used_total += 1
            self.save(update_fields=["credits_used_total", "updated_at"])
            return "pro"

        if self.plan == "free":
            self.reset_free_monthly_if_needed(monthly_amount=monthly_free_amount)

            if self.free_monthly_credits > 0:
                self.free_monthly_credits -= 1
                self.credits_used_total += 1
                self.save(update_fields=["free_monthly_credits", "credits_used_total", "updated_at"])
                return "free"

            if self.prepaid_credits > 0:
                self.prepaid_credits -= 1
                self.credits_used_total += 1
                self.save(update_fields=["prepaid_credits", "credits_used_total", "updated_at"])
                return "prepaid"

            raise ValueError("INSUFFICIENT_CREDITS")

        # prepaid plan
        if self.prepaid_credits > 0:
            self.prepaid_credits -= 1
            self.credits_used_total += 1
            self.save(update_fields=["prepaid_credits", "credits_used_total", "updated_at"])
            return "prepaid"

        raise ValueError("INSUFFICIENT_CREDITS")



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
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Success"),
        (STATUS_ERROR, "Error"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="kml_merge_jobs")
    anon_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
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
    
    
    # Lista de paths no storage (default_storage) de cada input salvo
    input_storage_paths = models.JSONField(blank=True, null=True)

    # Path do meta.json no storage
    meta_storage_path = models.CharField(max_length=1024, blank=True, null=True)

    # Auditoria (opcional, mas recomendo)
    download_email_sent_at = models.DateTimeField(blank=True, null=True)

    # Controle real de liberação/download
    download_unlocked = models.BooleanField(default=False, db_index=True)
    download_unlocked_at = models.DateTimeField(blank=True, null=True)

    download_unlock_source = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
    )

    download_credit_consumed = models.BooleanField(default=False)

    download_count = models.PositiveIntegerField(default=0)
    first_downloaded_at = models.DateTimeField(blank=True, null=True)
    last_downloaded_at = models.DateTimeField(blank=True, null=True)
    
    
    visitor_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    visitor_country = models.CharField(max_length=2, null=True, blank=True, db_index=True)
    visitor_country_name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["request_id"]),
            models.Index(fields=["-created_at", "-id"]),
            models.Index(fields=["anon_id"]),
            models.Index(fields=["visitor_ip"]),
            models.Index(fields=["plan"]),
            models.Index(fields=["visitor_country"]),
        ]

    def __str__(self):
        return f"KMLMergeJob({self.user_id}, {self.request_id}, {self.status})"


class MergeFeedback(models.Model):
    id = models.BigAutoField(primary_key=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kml_merge_feedbacks",
        db_index=True,
    )

    merge_job = models.ForeignKey(
        "kmltools.KMLMergeJob",
        on_delete=models.CASCADE,
        related_name="feedbacks",
        db_index=True,
    )

    message = models.TextField()

    # opcional (mas útil): origem/UX
    source = models.CharField(max_length=32, blank=True, default="ui")  # ui|email|admin|api

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["merge_job", "-created_at"]),
        ]

    def __str__(self):
        return f"MergeFeedback({self.user_id}, job={self.merge_job_id})"


class EmailMagicLink(models.Model):
    email = models.EmailField(db_index=True)
    token_hash = models.CharField(max_length=128, unique=True, db_index=True)

    used_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, default="")

    firebase_uid = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["email", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.email} - {'used' if self.used_at else 'pending'}"

    def is_valid(self):
        return not self.used_at and timezone.now() <= self.expires_at

    @staticmethod
    def make_raw_token():
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()