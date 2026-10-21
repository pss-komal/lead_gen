"""
email_service.py  —  Direct email integration using Gmail SMTP.

NO Mailchimp, NO SendGrid. Sends email directly via Gmail's SMTP server.

Method : Gmail SMTP with TLS (port 587)
Docs   : https://support.google.com/mail/answer/185833  (App Passwords)

Setup (one-time):
    1. Enable 2-Step Verification on your Gmail account
    2. Go to: Google Account → Security → App Passwords
    3. Generate an App Password (16 chars, no spaces)
    4. Put it in .env as GMAIL_APP_PASSWORD

Requires in .env:
    GMAIL_SENDER_EMAIL   = yourname@gmail.com
    GMAIL_APP_PASSWORD   = abcd efgh ijkl mnop   (16-char app password)
"""

import os
import logging
import smtplib
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("lead_gen.email_service")

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587           # TLS port


# ---------------------------------------------------------------------------
# Helper — get credentials
# ---------------------------------------------------------------------------

def _get_credentials():
    sender_email = os.getenv("GMAIL_SENDER_EMAIL")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not sender_email or not app_password:
        logger.error("GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set!")
        return None, None
    return sender_email, app_password


# ---------------------------------------------------------------------------
# Send a plain text email
# ---------------------------------------------------------------------------

def send_email(to_email: str, subject: str, body: str) -> dict:
    """
    Send a plain text email directly via Gmail SMTP.

    Parameters
    ----------
    to_email : str — recipient email address
    subject  : str — email subject line
    body     : str — plain text body

    Returns
    -------
    dict with success status and details
    """
    sender_email, app_password = _get_credentials()
    if not sender_email:
        return {"success": False, "error": "Gmail credentials not configured."}

    logger.info(
        "EMAIL/SEND — from: %s | to: %s | subject: %s",
        sender_email, to_email, subject,
    )

    msg = MIMEText(body, "plain")
    msg["From"]    = sender_email
    msg["To"]      = to_email
    msg["Subject"] = subject

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()                            # Upgrade to TLS
            smtp.login(sender_email, app_password)     # Authenticate
            smtp.sendmail(sender_email, to_email, msg.as_string())

        logger.info("EMAIL/SEND — successfully sent to: %s", to_email)
        return {
            "success":  True,
            "to":       to_email,
            "subject":  subject,
            "status":   "sent",
        }

    except smtplib.SMTPAuthenticationError:
        logger.error("EMAIL/SEND — Gmail authentication failed. Check App Password.")
        return {
            "success": False,
            "error":   "Gmail authentication failed. Ensure App Password is correct.",
        }
    except smtplib.SMTPException as exc:
        logger.error("EMAIL/SEND — SMTP error: %s", exc)
        return {"success": False, "error": f"SMTP error: {str(exc)}"}
    except Exception as exc:
        logger.error("EMAIL/SEND — unexpected error: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Send an HTML email
# ---------------------------------------------------------------------------

def send_html_email(to_email: str, subject: str, html_body: str) -> dict:
    """
    Send an HTML formatted email directly via Gmail SMTP.

    Parameters
    ----------
    to_email  : str — recipient email address
    subject   : str — email subject line
    html_body : str — HTML content (can include <b>, <a href>, <table>, etc.)
    """
    sender_email, app_password = _get_credentials()
    if not sender_email:
        return {"success": False, "error": "Gmail credentials not configured."}

    logger.info("EMAIL/SEND_HTML — to: %s | subject: %s", to_email, subject)

    msg = MIMEMultipart("alternative")
    msg["From"]    = sender_email
    msg["To"]      = to_email
    msg["Subject"] = subject

    # Attach HTML part (shown if email client supports HTML)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(sender_email, app_password)
            smtp.sendmail(sender_email, to_email, msg.as_string())

        logger.info("EMAIL/SEND_HTML — sent to: %s", to_email)
        return {"success": True, "to": to_email, "subject": subject, "status": "sent"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Gmail authentication failed. Check App Password."}
    except Exception as exc:
        logger.error("EMAIL/SEND_HTML — error: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Send lead details via email (convenience wrapper)
# ---------------------------------------------------------------------------

def send_lead_email(to_email: str, lead: dict, sender_name: str = "Lead Gen CRM") -> dict:
    """
    Convenience function — formats a lead as an HTML email and sends it.
    Useful for emailing lead details to a sales rep or manager.
    """
    subject = f"New Lead: {lead.get('title', 'Unknown')} — Score {lead.get('score', 0)}/100"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #2c7be5;">🎯 New Lead Found</h2>
        <table style="border-collapse: collapse; width: 100%;">
            <tr><td style="padding:8px; font-weight:bold;">Business</td>
                <td style="padding:8px;">{lead.get('title', 'N/A')}</td></tr>
            <tr style="background:#f9f9f9;">
                <td style="padding:8px; font-weight:bold;">Type</td>
                <td style="padding:8px;">{lead.get('lead_type', 'N/A')}</td></tr>
            <tr><td style="padding:8px; font-weight:bold;">Phone</td>
                <td style="padding:8px;">{lead.get('phone') or 'Not available'}</td></tr>
            <tr style="background:#f9f9f9;">
                <td style="padding:8px; font-weight:bold;">Address</td>
                <td style="padding:8px;">{lead.get('address') or 'N/A'}</td></tr>
            <tr><td style="padding:8px; font-weight:bold;">Category</td>
                <td style="padding:8px;">{lead.get('category') or 'N/A'}</td></tr>
            <tr style="background:#f9f9f9;">
                <td style="padding:8px; font-weight:bold;">Score</td>
                <td style="padding:8px;"><strong>{lead.get('score', 0)}/100</strong></td></tr>
            <tr><td style="padding:8px; font-weight:bold;">Source</td>
                <td style="padding:8px;">{lead.get('source', 'N/A')}</td></tr>
            <tr style="background:#f9f9f9;">
                <td style="padding:8px; font-weight:bold;">Link</td>
                <td style="padding:8px;">
                    <a href="{lead.get('link', '#')}">{lead.get('link') or 'N/A'}</a>
                </td></tr>
        </table>
        <br>
        <p style="color:#888; font-size:12px;">Sent by {sender_name}</p>
    </body>
    </html>
    """

    return send_html_email(to_email, subject, html_body)
