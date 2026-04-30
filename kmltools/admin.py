# kmltools/admin.py
from django.contrib import admin
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.utils.html import format_html

from .models import BillingProfile, WeeklyUsage, KMLMergeJob, MergeFeedback, UnlockFeedback, EmailMagicLink

from django.db.models import OuterRef, Subquery, IntegerField, Value, Case, When, F,  CharField, Count, Sum, TextField
from django.db.models.functions import Coalesce, Trim, Cast
from django.db.models.expressions import Func
from django.db.models import Count


import json

from django.urls import path, reverse
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.utils.safestring import mark_safe






# =========================
# Helpers
# =========================
def _email(obj):
    return getattr(getattr(obj, "user", None), "email", "") or ""

class SplitPart(Func):
    function = "SPLIT_PART"
    output_field = CharField()

# =========================
# BillingProfile
# =========================

@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_email",
        "auth_method",  # ✅ nova coluna
        "plan",
        "use_case",
        "usage_frequency",
        "is_unlimited_flag",
        "free_monthly_credits",
        "prepaid_credits",
        "credits_used_total",
        "stripe_subscription_id",
        "remove_from_mail_list",
        "onboarding_completed_at",
        "created_at",
        "stripe_customer_id",
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
        "remove_from_mail_list",
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
                "fields": ("user", "firebase_uid", 'remove_from_mail_list'),
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

    def auth_method(self, obj):
        email = (getattr(obj.user, "email", "") or "").strip().lower()

        if not email:
            return "—"

        used_link = EmailMagicLink.objects.filter(
            email__iexact=email,
            used_at__isnull=False,
        ).exists()

        if used_link:
            return format_html(
                '<span style="background:#e0f2fe;color:#075985;padding:3px 8px;border-radius:999px;font-weight:700;">Email link</span>'
            )

        return format_html(
            '<span style="background:#f3f4f6;color:#374151;padding:3px 8px;border-radius:999px;font-weight:700;">Google / Other</span>'
        )

    auth_method.short_description = "Auth"

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
    change_list_template = "admin/kmltools/kmlmergejob/change_list.html"
    show_full_result_count = False
    list_per_page = 100
    
    list_display = (
        "created_at_br",
        "user_email",
        "anon_id_compact",
        "anon_id_total_jobs",
        "plan_badge",
        "status_badge",
        "download_state",
        "merge_preview_button",
        "visitor_country_name",
        "visitor_ip",
        "visitor_ip_total_jobs",
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
        "download_unlocked",
        "download_unlock_source",
        "download_credit_consumed",
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

        "download_unlocked",
        "download_unlocked_at",
        "download_unlock_source",
        "download_credit_consumed",
        "download_count",
        "first_downloaded_at",
        "last_downloaded_at",
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

                    "download_unlocked",
                    "download_unlocked_at",
                    "download_unlock_source",
                    "download_credit_consumed",
                    "download_count",
                    "first_downloaded_at",
                    "last_downloaded_at",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        request._kml_admin_anon_counts = {}
        request._kml_admin_ip_counts = {}

        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .defer(
                "metrics",
                "input_filenames",
                "input_storage_paths",
                "storage_path",
                "meta_storage_path",
            )
        )

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)

        try:
            cl = response.context_data["cl"]
            result_list = list(cl.result_list)
        except Exception:
            return response

        anon_ids = sorted({
            obj.anon_id for obj in result_list
            if obj.anon_id
        })

        visitor_ips = sorted({
            obj.visitor_ip for obj in result_list
            if obj.visitor_ip
        })

        anon_counts = {}
        if anon_ids:
            anon_counts = {
                row["anon_id"]: row["total"]
                for row in (
                    KMLMergeJob.objects
                    .filter(anon_id__in=anon_ids)
                    .values("anon_id")
                    .annotate(total=Count("id"))
                )
            }

        ip_counts = {}
        if visitor_ips:
            ip_counts = {
                row["visitor_ip"]: row["total"]
                for row in (
                    KMLMergeJob.objects
                    .filter(visitor_ip__in=visitor_ips)
                    .values("visitor_ip")
                    .annotate(total=Count("id"))
                )
            }

        for obj in result_list:
            obj._anon_id_total_jobs = anon_counts.get(obj.anon_id, 0)
            obj._visitor_ip_total_jobs = ip_counts.get(obj.visitor_ip, 0)

        cl.result_list = result_list
        return response
    

    def user_email(self, obj):
        return obj.user.email if obj.user else "—"
    user_email.short_description = "Email"
    user_email.admin_order_field = "user__email"
    
    def created_at_br(self, obj):
        if not obj.created_at:
            return "—"

        dt = timezone.localtime(obj.created_at)

        return dt.strftime("%d/%m/%y - %H:%M")

    created_at_br.short_description = "Criado"
    created_at_br.admin_order_field = "created_at"


    def anon_id_compact(self, obj):
        anon = (obj.anon_id or "").strip()

        if not anon:
            return "—"

        if len(anon) <= 14:
            label = anon
        else:
            label = f"{anon[:6]}...{anon[-6:]}"

        return format_html(
            '<button type="button" class="kml-copy-anon-btn" data-copy="{}" '
            'title="Clique para copiar o anon_id completo" '
            'style="border:0;background:#f1f5f9;color:#334155;padding:3px 8px;'
            'border-radius:999px;font-weight:800;font-size:11px;cursor:pointer;'
            'white-space:nowrap;">{}</button>',
            anon,
            label,
        )

    anon_id_compact.short_description = "Anon ID"
    anon_id_compact.admin_order_field = "anon_id"
    
    def plan_badge(self, obj):
        plan = (getattr(obj, "plan", "") or "unknown").strip()

        plan_styles = {
            "free": {
                "bg": "#f3f4f6",
                "color": "#374151",
                "label": "Free",
            },
            "anonymous": {
                "bg": "#fef3c7",
                "color": "#92400e",
                "label": "Anonymous",
            },
            "prepaid": {
                "bg": "#dbeafe",
                "color": "#1d4ed8",
                "label": "Prepaid",
            },
            "pro": {
                "bg": "#dcfce7",
                "color": "#166534",
                "label": "Pro",
            },
            "pro_monthly": {
                "bg": "#dcfce7",
                "color": "#166534",
                "label": "Pro Monthly",
            },
            "pro_yearly": {
                "bg": "#ccfbf1",
                "color": "#0f766e",
                "label": "Pro Yearly",
            },
        }

        style = plan_styles.get(plan, {
            "bg": "#f3f4f6",
            "color": "#374151",
            "label": plan or "—",
        })

        return format_html(
            '<span style="background:{};color:{};padding:3px 8px;border-radius:999px;font-weight:700;white-space:nowrap;">{}</span>',
            style["bg"],
            style["color"],
            style["label"],
        )

    plan_badge.short_description = "Plan"
    plan_badge.admin_order_field = "plan"

    def status_badge(self, obj):
        status = (getattr(obj, "status", "") or "unknown").strip()

        status_styles = {
            "pending": {
                "bg": "#fef3c7",
                "color": "#92400e",
                "label": "Pending",
            },
            "processing": {
                "bg": "#dbeafe",
                "color": "#1d4ed8",
                "label": "Processing",
            },
            "done": {
                "bg": "#dcfce7",
                "color": "#166534",
                "label": "Done",
            },
            "completed": {
                "bg": "#dcfce7",
                "color": "#166534",
                "label": "Completed",
            },
            "success": {
                "bg": "#dcfce7",
                "color": "#166534",
                "label": "Success",
            },
            "failed": {
                "bg": "#fee2e2",
                "color": "#991b1b",
                "label": "Failed",
            },
            "error": {
                "bg": "#fee2e2",
                "color": "#991b1b",
                "label": "Error",
            },
            "cancelled": {
                "bg": "#f3f4f6",
                "color": "#374151",
                "label": "Cancelled",
            },
        }

        style = status_styles.get(status, {
            "bg": "#f3f4f6",
            "color": "#374151",
            "label": status or "—",
        })

        return format_html(
            '<span style="background:{};color:{};padding:3px 8px;border-radius:999px;font-weight:700;white-space:nowrap;">{}</span>',
            style["bg"],
            style["color"],
            style["label"],
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"
    
    def download_state(self, obj):
        if getattr(obj, "download_unlocked", False):
            source = (getattr(obj, "download_unlock_source", "") or "unlocked").strip()
            count = int(getattr(obj, "download_count", 0) or 0)

            if source in ("pro_monthly", "pro_yearly", "pro"):
                bg = "#dcfce7"
                color = "#166534"
                label = f"Unlocked · {source}"
            elif source == "prepaid_credit":
                bg = "#dbeafe"
                color = "#1d4ed8"
                label = "Unlocked · credit"
            elif source == "manual":
                bg = "#fef3c7"
                color = "#92400e"
                label = "Unlocked · manual"
            else:
                bg = "#f3f4f6"
                color = "#374151"
                label = f"Unlocked · {source}"

            return format_html(
                '<span style="background:{};color:{};padding:3px 8px;border-radius:999px;font-weight:700;white-space:nowrap;">{} · {}x</span>',
                bg,
                color,
                label,
                count,
            )

        return format_html(
            '<span style="background:#fee2e2;color:#991b1b;padding:3px 8px;border-radius:999px;font-weight:700;white-space:nowrap;">Locked</span>'
        )

    download_state.short_description = "Download"
    download_state.admin_order_field = "download_unlocked"

    def anon_id_total_jobs(self, obj):
        return getattr(obj, "_anon_id_total_jobs", 0)
    anon_id_total_jobs.short_description = "Merges / anon_id"

    def visitor_ip_total_jobs(self, obj):
        return getattr(obj, "_visitor_ip_total_jobs", 0)
    visitor_ip_total_jobs.short_description = "Merges / IP"
    
    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "<path:object_id>/merge-preview-json/",
                self.admin_site.admin_view(self.merge_preview_json_view),
                name="kmltools_kmlmergejob_merge_preview_json",
            ),
        ]

        return custom_urls + urls

    def merge_preview_button(self, obj):
        if not obj.pk:
            return "—"

        # Só mostra botão útil se tiver pelo menos metrics/meta/output/input.
        has_preview = bool(
            (obj.metrics or {}).get("preview_geojson")
            or (obj.metrics or {}).get("input_preview_geojson")
            or obj.meta_storage_path
            or obj.storage_path
            or obj.input_storage_paths
        )

        if not has_preview:
            return format_html(
                '<span style="background:#f3f4f6;color:#6b7280;padding:3px 8px;'
                'border-radius:999px;font-weight:700;white-space:nowrap;">No preview</span>'
            )

        url = reverse(
            "admin:kmltools_kmlmergejob_merge_preview_json",
            args=[obj.pk],
        )

        return format_html(
            '<button type="button" class="kml-preview-btn" data-preview-url="{}" '
            'style="background:#111827;color:#fff;border:0;padding:4px 10px;'
            'border-radius:999px;font-weight:800;cursor:pointer;white-space:nowrap;">'
            'Preview</button>',
            url,
        )

    merge_preview_button.short_description = "Antes / Depois"

    def _read_meta_json_from_storage(self, obj):
        if not obj.meta_storage_path:
            return {}

        try:
            with default_storage.open(obj.meta_storage_path, "rb") as f:
                raw = f.read()
            return json.loads(raw.decode("utf-8", errors="ignore")) or {}
        except Exception:
            return {}

    def _storage_url_or_none(self, path):
        if not path:
            return None

        try:
            return default_storage.url(path)
        except Exception:
            return None

    def merge_preview_json_view(self, request, object_id):
        obj = self.get_object(request, object_id)

        if not obj:
            return JsonResponse(
                {"ok": False, "detail": "Job não encontrado."},
                status=404,
            )

        metrics = obj.metrics or {}
        meta = {}

        input_preview_geojson = metrics.get("input_preview_geojson")
        output_preview_geojson = metrics.get("preview_geojson")
        files_report = metrics.get("files_report") or []

        # Fallback: tenta ler meta.json salvo no storage.
        if not input_preview_geojson or not output_preview_geojson or not files_report:
            meta = self._read_meta_json_from_storage(obj)

            input_preview_geojson = input_preview_geojson or meta.get("input_preview_geojson")
            output_preview_geojson = output_preview_geojson or meta.get("preview_geojson")
            files_report = files_report or meta.get("files_report") or []

        input_preview_geojson = input_preview_geojson or {
            "type": "FeatureCollection",
            "features": [],
        }

        output_preview_geojson = output_preview_geojson or {
            "type": "FeatureCollection",
            "features": [],
        }

        input_filenames = obj.input_filenames or []
        input_storage_paths = obj.input_storage_paths or []

        input_files = []
        for idx, name in enumerate(input_filenames):
            path = input_storage_paths[idx] if idx < len(input_storage_paths) else None
            input_files.append({
                "name": name,
                "path": path,
                "url": self._storage_url_or_none(path),
            })

        output_url = self._storage_url_or_none(obj.storage_path)

        total_polygons = int(obj.total_polygons or 0)
        output_polygons = int(obj.output_polygons or 0) if obj.output_polygons is not None else None
        merged_polygons = int(obj.merged_polygons or 0) if obj.merged_polygons is not None else None

        reduction_pct = None
        if total_polygons and output_polygons is not None:
            try:
                reduction_pct = round(((total_polygons - output_polygons) / total_polygons) * 100, 1)
            except Exception:
                reduction_pct = None

        payload = {
            "ok": True,
            "job": {
                "id": str(obj.id),
                "request_id": obj.request_id,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "status": obj.status,
                "plan": obj.plan,
                "user_email": obj.user.email if obj.user else None,
                "anon_id": obj.anon_id,
                "visitor_ip": obj.visitor_ip,
                "visitor_country_name": obj.visitor_country_name,
                "tol_m": obj.tol_m,
                "corridor_width_m": obj.corridor_width_m,
            },
            "download": {
                "unlocked": bool(obj.download_unlocked),
                "unlock_source": obj.download_unlock_source,
                "credit_consumed": bool(obj.download_credit_consumed),
                "count": int(obj.download_count or 0),
                "first_downloaded_at": obj.first_downloaded_at.isoformat() if obj.first_downloaded_at else None,
                "last_downloaded_at": obj.last_downloaded_at.isoformat() if obj.last_downloaded_at else None,
            },
            "metrics": {
                "total_files": int(obj.total_files or 0),
                "total_polygons": total_polygons,
                "output_polygons": output_polygons,
                "merged_polygons": merged_polygons,
                "input_area_ha": obj.input_area_ha,
                "output_area_ha": obj.output_area_ha,
                "reduction_pct": reduction_pct,
                "total_markers": int(metrics.get("total_markers") or meta.get("total_markers") or 0),
                "merge_mode": metrics.get("merge_mode") or meta.get("merge_mode") or "",
            },
            "files": {
                "input_files": input_files,
                "files_report": files_report,
                "output_storage_path": obj.storage_path,
                "output_url": output_url,
                "meta_storage_path": obj.meta_storage_path,
            },
            "geojson": {
                "input": input_preview_geojson,
                "output": output_preview_geojson,
            },
        }

        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})

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