"""
telegram_service.py  —  Telegram Bot API integration (100% FREE, no limits).

Setup (5 min, one-time):
  1. Open Telegram → search @BotFather → /newbot
  2. Give it a name → get BOT_TOKEN
  3. Message your bot → visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
  4. Copy 'chat.id' from the response → TELEGRAM_CHAT_ID

Requires in .env:
    TELEGRAM_BOT_TOKEN = 123456789:ABCdef...
    TELEGRAM_CHAT_ID   = -100123456789   (negative for groups, positive for personal)
"""

import os
import logging
import requests

logger = logging.getLogger("lead_gen.telegram")

TELEGRAM_API = "https://api.telegram.org"


def _get_credentials():
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set!")
        return None, None
    return token, chat_id


# ---------------------------------------------------------------------------
# Send plain text message
# ---------------------------------------------------------------------------

def send_message(text: str, chat_id: str = None) -> dict:
    """Send a plain text message to the configured Telegram chat."""
    token, default_chat = _get_credentials()
    if not token:
        return {"success": False, "error": "Telegram credentials not configured."}

    target_chat = chat_id or default_chat

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json={
                "chat_id":    target_chat,
                "text":       text,
                "parse_mode": "Markdown",   # supports *bold*, _italic_, `code`
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            logger.info("Telegram message sent to chat_id: %s", target_chat)
            return {"success": True, "message_id": data["result"]["message_id"]}
        else:
            logger.error("Telegram error: %s", data.get("description"))
            return {"success": False, "error": data.get("description")}
    except Exception as exc:
        logger.error("Telegram send error: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Send formatted lead card
# ---------------------------------------------------------------------------

def send_lead_notification(lead: dict, chat_id: str = None) -> dict:
    """Send a beautifully formatted lead card to Telegram."""
    score = lead.get("score", 0)
    score_emoji = "🔥" if score >= 70 else "⚡" if score >= 50 else "📋"

    text = (
        f"{score_emoji} *New Lead Found!*\n\n"
        f"🏢 *Business:* {lead.get('title', 'N/A')}\n"
        f"🏷️ *Type:* {lead.get('lead_type', 'N/A')}\n"
        f"📞 *Phone:* {lead.get('phone') or 'Not available'}\n"
        f"📍 *Address:* {lead.get('address') or 'N/A'}\n"
        f"🗂️ *Category:* {lead.get('category') or 'N/A'}\n"
        f"⭐ *Score:* `{score}/100`\n"
        f"🔗 *Link:* {lead.get('link') or 'N/A'}\n"
        f"📡 *Source:* {lead.get('source', 'N/A')}"
    )
    return send_message(text, chat_id)


# ---------------------------------------------------------------------------
# Send high-score alert (only for leads above threshold)
# ---------------------------------------------------------------------------

def send_high_score_alert(leads: list, threshold: int = 70, chat_id: str = None) -> dict:
    """
    Filter leads above score threshold and send a summary alert to Telegram.
    Used after any lead search to instantly notify team of top leads.
    """
    top_leads = [l for l in leads if l.get("score", 0) >= threshold]

    if not top_leads:
        return {"success": True, "sent": 0, "message": "No leads above threshold."}

    lines = [f"🎯 *{len(top_leads)} HIGH-SCORE LEADS FOUND!*\n"]
    for lead in top_leads:
        lines.append(
            f"• *{lead.get('title')}* — Score: `{lead.get('score')}/100`\n"
            f"  📞 {lead.get('phone') or 'No phone'} | 📍 {(lead.get('address') or '')[:40]}"
        )

    result = send_message("\n".join(lines), chat_id)
    result["high_score_leads_sent"] = len(top_leads)
    return result


# ---------------------------------------------------------------------------
# Send batch search summary
# ---------------------------------------------------------------------------

def send_search_summary(product_name: str, region: str, total: int,
                        score_summary: dict, chat_id: str = None) -> dict:
    """Send a quick summary after a lead search completes."""
    text = (
        f"✅ *Lead Search Complete!*\n\n"
        f"🔍 Product : `{product_name}`\n"
        f"📍 Region  : `{region}`\n"
        f"📊 Total   : `{total} leads`\n"
        f"⭐ Scores  : Max `{score_summary.get('max', 0)}` | "
        f"Avg `{score_summary.get('avg', 0)}` | "
        f"Min `{score_summary.get('min', 0)}`"
    )
    return send_message(text, chat_id)
