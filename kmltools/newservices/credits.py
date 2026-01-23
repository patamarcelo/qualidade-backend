# kmltools/services/credits.py
from dataclasses import dataclass
from django.db import transaction
from django.utils import timezone

from kmltools.models import BillingProfile


class NoCreditsLeft(Exception):
    pass


@dataclass
class CreditConsumption:
    kind: str  # "pro" | "prepaid" | "free"


def _is_pro(bp: BillingProfile) -> bool:
    return bp.plan in ("pro_monthly", "pro_yearly") or bool(
        getattr(bp, "is_unlimited", False)
    )


@transaction.atomic
def reserve_one_credit(user) -> CreditConsumption:
    """
    Reserva/consome 1 crédito de forma atômica.
    Usa APENAS campos existentes no BillingProfile:
      - free_monthly_credits
      - prepaid_credits
      - credits_used_total
      - is_unlimited / plan
    """
    bp = BillingProfile.objects.select_for_update().get(user=user)

    # UX: se free, garante reset mensal antes de consumir
    # (assumindo que esse método existe, pois você usa em /me e /usage)
    try:
        if bp.plan == "free":
            bp.reset_free_monthly_if_needed(
                monthly_amount=2
            )  # mantém alinhado ao seu FREE_MONTHLY_CREDITS
            bp.refresh_from_db()
    except Exception:
        # não impede consumo; apenas não reseta aqui
        pass

    if _is_pro(bp):
        # Pro é ilimitado: apenas contabiliza total se você quiser
        try:
            bp.credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0) + 1
            bp.save(update_fields=["credits_used_total", "updated_at"])
        except Exception:
            pass
        return CreditConsumption(kind="pro")

    prepaid = int(getattr(bp, "prepaid_credits", 0) or 0)
    free = int(getattr(bp, "free_monthly_credits", 0) or 0)

    if prepaid > 0:
        bp.prepaid_credits = prepaid - 1
        bp.credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0) + 1
        bp.save(update_fields=["prepaid_credits", "credits_used_total", "updated_at"])
        return CreditConsumption(kind="prepaid")

    if free > 0:
        bp.free_monthly_credits = free - 1
        bp.credits_used_total = int(getattr(bp, "credits_used_total", 0) or 0) + 1
        bp.save(
            update_fields=["free_monthly_credits", "credits_used_total", "updated_at"]
        )
        return CreditConsumption(kind="free")

    raise NoCreditsLeft("NO_CREDITS_LEFT")


@transaction.atomic
def refund_one_credit(user, consumption: CreditConsumption):
    """
    Devolve 1 crédito caso o merge falhe (best-effort).
    Importante: Pro não devolve nada.
    """
    if not consumption or consumption.kind == "pro":
        return

    bp = BillingProfile.objects.select_for_update().get(user=user)

    if consumption.kind == "prepaid":
        bp.prepaid_credits = int(getattr(bp, "prepaid_credits", 0) or 0) + 1
        bp.save(update_fields=["prepaid_credits", "updated_at"])
        return

    if consumption.kind == "free":
        bp.free_monthly_credits = int(getattr(bp, "free_monthly_credits", 0) or 0) + 1
        bp.save(update_fields=["free_monthly_credits", "updated_at"])
        return
