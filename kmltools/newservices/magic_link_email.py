import os
import resend

resend.api_key = os.getenv("RESEND_EMAIL_API_KEY_KMLUNIFIER")

FROM_EMAIL = os.getenv("KML_DEFAULT_FROM", "KML Unifier <team@kmlunifier.com>")
REPLY_EMAIL = os.getenv("KML_REPLY_EMAIL", "contact@kmlunifier.com")


def send_magic_login_email(*, to_email: str, link: str):
    site_url = os.getenv("KML_SITE_URL", "https://kmlunifier.com").rstrip("/")

    subject = "Your secure sign-in link for KML Unifier"

    html = f"""
<!doctype html>
<html>
  <body style="margin:0;background:#f6f3ee;padding:24px">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">
      Use this secure link to sign in and unlock your KML file.
    </div>

    <div style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:18px;
                border:1px solid #e8dfd2;box-shadow:0 12px 34px rgba(98,85,70,0.10);
                overflow:hidden;font-family:Arial,sans-serif;color:#2d2923">

      <div style="padding:20px 22px;background:linear-gradient(135deg,#8d6e47,#b08968);color:#fff">
        <div style="font-size:14px;opacity:.9">KML Unifier</div>
        <div style="font-size:24px;font-weight:900;margin-top:5px">Sign in securely</div>
        <div style="font-size:13px;opacity:.86;margin-top:6px">
          Your link is valid for a limited time.
        </div>
      </div>

      <div style="padding:22px">
        <p style="margin:0 0 14px;color:#4b4338;line-height:1.5">
          Click the button below to finish signing in and continue with your KML merge.
        </p>

        <div style="margin:22px 0">
          <a href="{link}"
             style="display:inline-block;background:#8d6e47;color:#fff;text-decoration:none;
                    padding:13px 18px;border-radius:14px;font-weight:900">
            Sign in to KML Unifier
          </a>
        </div>

        <p style="margin:0;color:#7a7165;font-size:13px;line-height:1.5">
          If the button does not work, copy and paste this link into your browser:
        </p>

        <p style="word-break:break-all;color:#8d6e47;font-size:13px;line-height:1.5">
          {link}
        </p>

        <p style="margin:18px 0 0;color:#7a7165;font-size:13px;line-height:1.5">
          If you did not request this email, you can ignore it.
        </p>
      </div>

      <div style="padding:14px 22px;border-top:1px solid #eee5da;background:#fcfaf7;color:#9a9185;font-size:12px">
        Sent by KML Unifier • <a href="{site_url}" style="color:#8d6e47;text-decoration:none">{site_url}</a>
      </div>
    </div>
  </body>
</html>
""".strip()

    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "replyTo": REPLY_EMAIL,
    })