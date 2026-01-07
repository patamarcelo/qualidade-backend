# kmltools/admin.py
from django.contrib import admin
from .models import BillingProfile, WeeklyUsage


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
