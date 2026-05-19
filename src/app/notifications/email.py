"""SMTP email sender using Gmail."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.app.core.config import settings

logger = logging.getLogger("ai_parking.notifications.email")


def send_email(to_email: str, subject: str, body: str, html_body: str = None):
    """Send email via SMTP. Uses config from .env."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured. Skipping email to %s", to_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    if html_body:
        msg.attach(MIMEText(html_body, "html"))
    else:
        # Determine severity color from subject
        if "[CRITICAL]" in subject:
            badge_color = "#dc2626"
            badge_text = "CRITICAL"
        elif "[HIGH]" in subject:
            badge_color = "#ea580c"
            badge_text = "HIGH"
        elif "[MEDIUM]" in subject:
            badge_color = "#d97706"
            badge_text = "MEDIUM"
        elif "[LOW]" in subject:
            badge_color = "#0d9488"
            badge_text = "LOW"
        else:
            badge_color = "#475569"
            badge_text = "ALERT"

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background-color: #f8fafc;">
            <div style="max-width: 560px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: white;">
                <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 24px 28px;">
                    <h2 style="margin: 0; color: white; font-size: 18px; font-weight: 600;">AI Parking Central</h2>
                </div>
                <div style="padding: 28px;">
                    <div style="margin-bottom: 20px;">
                        <span style="display: inline-block; background-color: {badge_color}; color: white; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px; letter-spacing: 0.5px;">{badge_text}</span>
                    </div>
                    <p style="font-size: 15px; color: #1e293b; line-height: 1.6; margin: 0 0 24px 0;">{body}</p>
                    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0; line-height: 1.5;">
                        This is an automated alert from AI Parking Central.<br>
                        Manage your notification preferences in Settings.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

    try:
        if settings.SMTP_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
        server.quit()

        logger.info("Email sent to %s: %s", to_email, subject)
        return True

    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False
