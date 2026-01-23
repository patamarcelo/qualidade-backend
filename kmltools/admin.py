# kmltools/admin.py
from django.contrib import admin
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth import get_user_model

from .models import BillingProfile, WeeklyUsage, KMLMergeJob


# =========================
# Helpers
# =========================
def _email(obj):
    return getattr(getattr(obj, "user", None), "email", "") or ""


# =========================
# BillingProfile
# =========================
@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_email",
        "firebase_uid",
        "plan",
        "is_unlimited_flag",
        "free_monthly_credits",
        "prepaid_credits",
        "credits_used_total",
        "free_month_key",
        "stripe_customer_id",
        "stripe_subscription_id",
        "current_period_end",
        "cancel_at_period_end",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "plan",
        "cancel_at_period_end",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__email",
        "user__username",
        "firebase_uid",
        "stripe_customer_id",
        "stripe_subscription_id",
    )

    autocomplete_fields = ("user",)
    ordering = ("-updated_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "is_unlimited_flag",
        "current_month_key_display",
        "credits_summary",
    )

    fieldsets = (
        (
            "User",
            {
                "fields": ("user", "firebase_uid"),
            },
        ),
        (
            "Plan",
            {
                "fields": ("plan", "is_unlimited_flag"),
                "description": (
                    "Nota: o plano 'pro' é legado (mantido apenas para não quebrar usuários antigos)."
                ),
            },
        ),
        (
            "Credits",
            {
                "fields": (
                    "free_monthly_credits",
                    "free_month_key",
                    "current_month_key_display",
                    "prepaid_credits",
                    "credits_used_total",
                    "credits_summary",
                )
            },
        ),
        (
            "Stripe",
            {
                "fields": (
                    "stripe_customer_id",
                    "stripe_subscription_id",
                    "current_period_end",
                    "cancel_at_period_end",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    actions = (
        "reset_free_to_2_now",
        "force_sync_month_key_now",
        "migrate_legacy_pro_to_pro_monthly",
        "add_10_prepaid_credits",
    )

    def user_email(self, obj):
        return _email(obj)

    user_email.short_description = "Email"
    user_email.admin_order_field = "user__email"

    def is_unlimited_flag(self, obj):
        # usa property do model
        return bool(getattr(obj, "is_unlimited", False))

    is_unlimited_flag.short_description = "Unlimited?"
    is_unlimited_flag.boolean = True

    def current_month_key_display(self, obj):
        # só para inspeção rápida (não altera DB)
        today = timezone.localdate()
        return timezone.datetime(today.year, today.month, 1).date()

    current_month_key_display.short_description = "Current month key (YYYY-MM-01)"

    def credits_summary(self, obj):
        # resumo legível no admin
        parts = [
            f"free_monthly_credits={obj.free_monthly_credits}",
            f"prepaid_credits={obj.prepaid_credits}",
            f"credits_used_total={obj.credits_used_total}",
            f"free_month_key={obj.free_month_key}",
        ]
        if obj.plan == "pro":
            parts.append("LEGACY_PLAN=pro")
        return " | ".join(parts)

    credits_summary.short_description = "Credits summary"

    # -------- actions --------
    @admin.action(
        description="Reset FREE credits to 2 for current month (only free plan)"
    )
    def reset_free_to_2_now(self, request, queryset):
        updated = 0
        for bp in queryset.select_related("user"):
            if bp.plan != "free":
                continue
            bp.reset_free_monthly_if_needed(monthly_amount=2, now=timezone.localdate())
            # o reset acima já salva quando necessário; garantimos 2 mesmo no mesmo mês:
            if bp.free_monthly_credits != 2:
                bp.free_monthly_credits = 2
                bp.free_month_key = timezone.datetime(
                    timezone.localdate().year, timezone.localdate().month, 1
                ).date()
                bp.save(
                    update_fields=[
                        "free_monthly_credits",
                        "free_month_key",
                        "updated_at",
                    ]
                )
            updated += 1
        self.message_user(request, f"Updated {updated} profile(s).")

    @admin.action(description="Force sync free_month_key to current month (free only)")
    def force_sync_month_key_now(self, request, queryset):
        mk = timezone.datetime(
            timezone.localdate().year, timezone.localdate().month, 1
        ).date()
        updated = queryset.filter(plan="free").update(free_month_key=mk)
        self.message_user(request, f"Updated free_month_key for {updated} profile(s).")

    @admin.action(description="Migrate legacy plan 'pro' -> 'pro_monthly'")
    def migrate_legacy_pro_to_pro_monthly(self, request, queryset):
        updated = queryset.filter(plan="pro").update(plan="pro_monthly")
        self.message_user(
            request, f"Migrated {updated} legacy 'pro' profile(s) to 'pro_monthly'."
        )

    @admin.action(description="Add +10 prepaid credits")
    def add_10_prepaid_credits(self, request, queryset):
        updated = 0
        for bp in queryset:
            bp.prepaid_credits = (bp.prepaid_credits or 0) + 10
            bp.save(update_fields=["prepaid_credits", "updated_at"])
            updated += 1
        self.message_user(
            request, f"Added +10 prepaid credits for {updated} profile(s)."
        )


# =========================
# WeeklyUsage
# =========================
@admin.register(WeeklyUsage)
class WeeklyUsageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_email",
        "week",
        "count",
        "updated_at",
    )

    list_filter = ("week", "updated_at")
    search_fields = ("user__email", "user__username", "week")
    autocomplete_fields = ("user",)
    ordering = ("-updated_at",)

    readonly_fields = ("updated_at",)

    def user_email(self, obj):
        return _email(obj)

    user_email.short_description = "Email"
    user_email.admin_order_field = "user__email"


# =========================
# KMLMergeJob
# =========================
@admin.register(KMLMergeJob)
class KMLMergeJobAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user_email",
        "plan",
        "status",
        "tol_m",
        "corridor_width_m",
        "total_files",
        "total_polygons",
        "output_polygons",
        "merged_polygons",
        "input_area_ha",
        "output_area_ha",
        "request_id",
    )

    list_filter = (
        "status",
        "plan",
        "created_at",
    )

    search_fields = (
        "request_id",
        "user__email",
        "user__username",
    )

    autocomplete_fields = ("user",)

    readonly_fields = (
        "id",
        "created_at",
        "request_id",
        "metrics",
        "input_filenames",
        "storage_path",
    )

    ordering = ("-created_at",)

    fieldsets = (
        (
            "Identificação",
            {
                "fields": ("id", "user", "request_id", "status", "plan", "created_at"),
            },
        ),
        (
            "Parâmetros do Merge",
            {
                "fields": ("tol_m", "corridor_width_m"),
            },
        ),
        (
            "Entrada",
            {
                "fields": ("total_files", "total_polygons", "input_filenames"),
            },
        ),
        (
            "Resultado / Métricas",
            {
                "fields": (
                    "output_polygons",
                    "merged_polygons",
                    "input_area_m2",
                    "input_area_ha",
                    "output_area_m2",
                    "output_area_ha",
                    "metrics",
                ),
            },
        ),
        (
            "Storage",
            {
                "fields": ("storage_path",),
            },
        ),
    )

    def user_email(self, obj):
        return _email(obj)

    user_email.short_description = "Email"
    user_email.admin_order_field = "user__email"
