# kmltools/admin.py
from django.contrib import admin
from .models import BillingProfile, WeeklyUsage, KMLMergeJob


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user_email", "firebase_uid", "plan", "stripe_customer_id", "created_at")
    list_filter = ("plan", "created_at")
    search_fields = ("user__email", "firebase_uid", "stripe_customer_id")
    autocomplete_fields = ("user",)
    ordering = ("-created_at",)

    def user_email(self, obj):
        return getattr(obj.user, "email", "")
    user_email.short_description = "Email"


@admin.register(WeeklyUsage)
class WeeklyUsageAdmin(admin.ModelAdmin):
    list_display = ("id", "user_email", "week", "count", "updated_at")
    list_filter = ("week", "updated_at")
    search_fields = ("user__email", "week")
    autocomplete_fields = ("user",)
    ordering = ("-updated_at",)

    def user_email(self, obj):
        return getattr(obj.user, "email", "")
    user_email.short_description = "Email"


@admin.register(KMLMergeJob)
class KMLMergeJobAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "plan",
        "status",
        "total_files",
        "total_polygons",
        "output_polygons",
        "input_area_ha",
        "output_area_ha",
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
        ("Identificação", {
            "fields": ("id", "user", "request_id", "status", "plan", "created_at"),
        }),
        ("Parâmetros do Merge", {
            "fields": ("tol_m", "corridor_width_m"),
        }),
        ("Entrada", {
            "fields": ("total_files", "total_polygons", "input_filenames"),
        }),
        ("Resultado / Métricas", {
            "fields": (
                "output_polygons",
                "merged_polygons",
                "input_area_m2",
                "input_area_ha",
                "output_area_m2",
                "output_area_ha",
                "metrics",
            ),
        }),
        ("Storage", {
            "fields": ("storage_path",),
        }),
    )
