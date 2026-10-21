"""
whatsapp_service.py  —  Direct integration with WhatsApp Business API (Meta).

NO third-party tool. Calls Meta's WhatsApp Cloud API directly.

API used : WhatsApp Business Cloud API
Docs     : https://developers.facebook.com/docs/whatsapp/cloud-api/messages

Use cases in Lead Gen:
  - Send a WhatsApp message to a lead's phone number
  - Send a follow-up to leads after CRM action

Requires in .env:
    WHATSAPP_PHONE_NUMBER_ID = 1234567890   (your Meta business phone number ID)
    WHATSAPP_ACCESS_TOKEN    = EAAxxxxxxxx  (permanent or temporary token from Meta)
"""

import os
import logging
import requests

logger = logging.getLogger("lead_gen.whatsapp_service")

META_GRAPH_URL = "https://graph.facebook.com/v18.0"


# ---------------------------------------------------------------------------
# Helper — get credentials
# ---------------------------------------------------------------------------

def _get_credentials():
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    access_token    = os.getenv("WHATSAPP_ACCESS_TOKEN")
    if not phone_number_id or not access_token:
        logger.error("WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN not set!")
        return None, None
    return phone_number_id, access_token


# ---------------------------------------------------------------------------
# Send a plain text WhatsApp message
# ---------------------------------------------------------------------------

def send_text_message(to_phone: str, message: str) -> dict:
    """
    Send a plain text WhatsApp message to a phone number.

    Parameters
    ----------
    to_phone : str — recipient phone with country code, NO '+' or spaces
                     e.g. '919876543210'  (91 = India, 9876543210 = number)
    message  : str — the text message to send

    Returns
    -------
    dict with success status and Meta response details
    """
    phone_number_id, access_token = _get_credentials()
    if not phone_number_id:
        return {"success": False, "error": "WhatsApp credentials not configured."}

    # Sanitize phone — remove +, spaces, dashes
    clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")

    logger.info(
        "WHATSAPP/SEND_TEXT — to: %s | message length: %d chars",
        clean_phone, len(message),
    )

    url     = f"{META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                clean_phone,
        "type":              "text",
        "text": {
            "preview_url": False,
            "body":        message,
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        logger.info("WhatsApp API status: %d", response.status_code)

        data = response.json()

        if response.status_code == 200:
            message_id = data.get("messages", [{}])[0].get("id", "")
            logger.info("WhatsApp message sent! message_id: %s", message_id)
            return {
                "success":    True,
                "message_id": message_id,
                "to":         clean_phone,
                "status":     "sent",
            }
        else:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error("WhatsApp send failed: %s", error_msg)
            return {"success": False, "error": error_msg}

    except Exception as exc:
        logger.error("WHATSAPP/SEND_TEXT exception: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Send a WhatsApp Template message (required for first-time contact)
# ---------------------------------------------------------------------------

def send_template_message(to_phone: str, template_name: str, language_code: str = "en_US") -> dict:
    """
    Send a pre-approved WhatsApp template message.

    Template messages are REQUIRED when contacting a user for the FIRST TIME
    (i.e. they haven't messaged you in the last 24 hours).

    The template must first be created and approved in Meta Business Manager.

    Parameters
    ----------
    to_phone       : str — recipient phone with country code (no + or spaces)
    template_name  : str — name of the approved template (e.g. 'lead_followup')
    language_code  : str — language code of the template (default: 'en_US')
    """
    phone_number_id, access_token = _get_credentials()
    if not phone_number_id:
        return {"success": False, "error": "WhatsApp credentials not configured."}

    clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")

    logger.info(
        "WHATSAPP/SEND_TEMPLATE — to: %s | template: %s",
        clean_phone, template_name,
    )

    url     = f"{META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":                clean_phone,
        "type":              "template",
        "template": {
            "name":     template_name,
            "language": {"code": language_code},
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        data     = response.json()

        if response.status_code == 200:
            message_id = data.get("messages", [{}])[0].get("id", "")
            logger.info("WhatsApp template sent! message_id: %s", message_id)
            return {
                "success":    True,
                "message_id": message_id,
                "to":         clean_phone,
                "template":   template_name,
                "status":     "sent",
            }
        else:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error("WhatsApp template failed: %s", error_msg)
            return {"success": False, "error": error_msg}

    except Exception as exc:
        logger.error("WHATSAPP/SEND_TEMPLATE exception: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Send lead details to a WhatsApp number (convenience wrapper)
# ---------------------------------------------------------------------------

def send_lead_to_whatsapp(to_phone: str, lead: dict) -> dict:
    """
    Convenience function — formats a lead dict and sends it as a WhatsApp message.
    Useful for notifying a sales rep about a new lead immediately.
    """
    message = (
        f"🎯 *New Lead Found!*\n\n"
        f"*Business:* {lead.get('title', 'N/A')}\n"
        f"*Type:* {lead.get('lead_type', 'N/A')}\n"
        f"*Phone:* {lead.get('phone') or 'Not available'}\n"
        f"*Address:* {lead.get('address') or 'N/A'}\n"
        f"*Category:* {lead.get('category') or 'N/A'}\n"
        f"*Score:* {lead.get('score', 0)}/100\n"
        f"*Link:* {lead.get('link') or 'N/A'}\n"
        f"*Source:* {lead.get('source', 'N/A')}"
    )
    return send_text_message(to_phone, message)
