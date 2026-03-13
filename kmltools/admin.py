# kmltools/admin.py
from django.contrib import admin
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth import get_user_model

from .models import BillingProfile, WeeklyUsage, KMLMergeJob, MergeFeedback, UnlockFeedback

from django.db.models import Count
from django.utils.html import format_html




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
        "plan",
        "use_case",           # Novo campo na listagem
        "usage_frequency",    # Novo campo na listagem
        "is_unlimited_flag",
        "free_monthly_credits",
        "prepaid_credits",
        "credits_used_total",
        "onboarding_completed_at", # Útil para ver ativação
        "created_at",
        "stripe_customer_id",
        "stripe_subscription_id",
        "current_period_end",
        "country_name", 
    )

    list_filter = (
        "plan",
        "use_case",           # Filtro para segmentação
        "usage_frequency",    # Filtro para segmentação
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
        "onboarding_completed_at",
    )

    fieldsets = (
        (
            "User",
            {
                "fields": ("user", "firebase_uid"),
            },
        ),
        (
            "Onboarding & ICP", # Nova Seção
            {
                "fields": (
                    "use_case",
                    "usage_frequency",
                    "onboarding_completed_at",
                    "onboarding_skipped_count",
                ),
                "description": "Dados coletados durante o onboarding para perfil de cliente (ICP).",
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
        "anon_id",
        "plan",
        "status",
        "visitor_country_name",
        "visitor_ip",
        "tol_m",
        "corridor_width_m",
        "total_files",
        "total_polygons",
        "output_polygons",
        "merged_polygons",
        "output_area_ha",
        "request_id",
    )

    list_filter = (
        "status",
        "plan",
        "visitor_country",
        "created_at",
    )

    search_fields = (
        "request_id",
        "anon_id",
        "visitor_ip",
        "visitor_country",
        "visitor_country_name",
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
        "input_storage_paths",
        "meta_storage_path",
        "storage_path",
        "visitor_ip",
        "visitor_country",
        "visitor_country_name",
        "download_email_sent_at",
    )

    ordering = ("-created_at",)

    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "id",
                    "user",
                    "anon_id",
                    "request_id",
                    "status",
                    "plan",
                    "created_at",
                ),
            },
        ),
        (
            "Visitor / Geo",
            {
                "fields": (
                    "visitor_ip",
                    "visitor_country",
                    "visitor_country_name",
                ),
            },
        ),
        (
            "Parâmetros do Merge",
            {
                "fields": (
                    "tol_m",
                    "corridor_width_m",
                ),
            },
        ),
        (
            "Entrada",
            {
                "fields": (
                    "total_files",
                    "total_polygons",
                    "input_filenames",
                    "input_storage_paths",
                ),
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
            "Storage / Auditoria",
            {
                "fields": (
                    "storage_path",
                    "meta_storage_path",
                    "download_email_sent_at",
                ),
            },
        ),
    )

    def user_email(self, obj):
        return obj.user.email if obj.user else "—"

    user_email.short_description = "Email"
    user_email.admin_order_field = "user__email"

@admin.register(MergeFeedback)
class MergeFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "merge_job", "source", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("message", "user__email", "merge_job__id", "merge_job__request_id")
    ordering = ("-created_at",)








@admin.register(UnlockFeedback)
class UnlockFeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_email",
        "use_case_display",
        "frequency",
        "willingness",
        "price_expectation",
        "created_at",
    )

    list_filter = (
        "use_case",
        "frequency",
        "willingness",
        "price_expectation",
        "created_at",
    )

    search_fields = (
        "user__email",
        "anon_id",
        "other_use_case_text",
    )

    readonly_fields = (
        "user",
        "anon_id",
        "use_case",
        "other_use_case_text",
        "frequency",
        "willingness",
        "price_expectation",
        "created_at",
    )

    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50

    actions = ["export_as_csv"]

    # -----------------------------
    # Coluna calculada - email
    # -----------------------------
    def user_email(self, obj):
        return obj.user.email if obj.user else "Anonymous"
    user_email.short_description = "User Email"

    # -----------------------------
    # Coluna calculada - use case com "other"
    # -----------------------------
    def use_case_display(self, obj):
        if obj.use_case == "other" and obj.other_use_case_text:
            return format_html(
                "<strong>Other:</strong> {}",
                obj.other_use_case_text
            )
        return obj.use_case
    use_case_display.short_description = "Use Case"

    # -----------------------------
    # CSV export
    # -----------------------------
    def export_as_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=unlock_feedback.csv"

        writer = csv.writer(response)
        writer.writerow([
            "ID",
            "User Email",
            "Anon ID",
            "Use Case",
            "Other Use Case Text",
            "Frequency",
            "Willingness",
            "Price Expectation",
            "Created At",
        ])

        for obj in queryset:
            writer.writerow([
                obj.id,
                obj.user.email if obj.user else "",
                obj.anon_id,
                obj.use_case,
                obj.other_use_case_text or "",
                obj.frequency,
                obj.willingness,
                obj.price_expectation,
                obj.created_at,
            ])

        return response

    export_as_csv.short_description = "Export selected as CSV"