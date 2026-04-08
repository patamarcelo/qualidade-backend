# kmltools/email_campaigns.py
import time

from kmltools.models import BillingProfile
from kmltools.emailer import send_reactivation_email


def get_billing_profile_emails():
    return list(
        BillingProfile.objects
        .select_related("user")
        .filter(remove_from_mail_list=False)
        .exclude(user__email__isnull=True)
        .exclude(user__email__exact="")
        .values_list("user__email", flat=True)
        .distinct()
    )


def print_billing_profile_emails():
    emails = get_billing_profile_emails()

    print(f"Total emails: {len(emails)}")
    print("-----")
    for email in emails:
        print(email)

    return emails


def send_reactivation_campaign(delay_seconds=2, only_emails=None, limit=None, dry_run=False):
    if only_emails:
        emails = list(only_emails)
    else:
        emails = get_billing_profile_emails()

    if limit is not None:
        emails = emails[:limit]

    print(f"Total target emails: {len(emails)}")
    print("-----")

    sent = 0
    failed = 0
    errors = []

    for email in emails:
        try:
            if dry_run:
                print(f"[DRY RUN] Enviaria para: {email}")
            else:
                print(f"Enviando para: {email}")
                send_reactivation_email(email)
                sent += 1

                if delay_seconds:
                    time.sleep(delay_seconds)

        except Exception as e:
            failed += 1
            errors.append((email, str(e)))
            print(f"Erro em {email}: {e}")

    print("-----")
    print(f"Enviados: {sent}")
    print(f"Erros: {failed}")

    if errors:
        print("-----")
        print("Lista de erros:")
        for email, err in errors:
            print(f"{email}: {err}")

    return {
        "total": len(emails),
        "sent": sent,
        "failed": failed,
        "errors": errors,
    }