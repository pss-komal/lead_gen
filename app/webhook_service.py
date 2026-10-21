"""
webhook_service.py  —  Slack & Discord webhook notifications (100% FREE).

Slack   : Create Incoming Webhook at https://api.slack.com/apps
Discord : Server Settings → Integrations → Webhooks → New Webhook

Requires in .env:
    SLACK_WEBHOOK_URL   = https://hooks.slack.com/services/T.../B.../xxx
    DISCORD_WEBHOOK_URL = https://discord.com/api/webhooks/id/token
"""

import os
import logging
import requests

logger = logging.getLogger("lead_gen.webhook")


def _post_json(url: str, payload: dict, service: str) -> dict:
    """Generic POST helper for webhook calls."""
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code in (200, 204):
            logger.info("%s webhook sent successfully.", service)
            return {"success": True, "service": service}
        else:
            logger.error("%s webhook failed: %d — %s", service, resp.status_code, resp.text[:200])
            return {"success": False, "service": service, "error": resp.text[:200]}
    except Exception as exc:
        logger.error("%s webhook exception: %s", service, exc)
        return {"success": False, "service": service, "error": str(exc)}


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

def send_slack_message(text: str, webhook_url: str = None) -> dict:
    """Send a plain text message to Slack."""
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return {"success": False, "error": "SLACK_WEBHOOK_URL not set."}
    return _post_json(url, {"text": text}, "Slack")


def send_slack_lead(lead: dict, webhook_url: str = None) -> dict:
    """Send a rich Slack Block Kit lead card."""
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return {"success": False, "error": "SLACK_WEBHOOK_URL not set."}

    score = lead.get("score", 0)
    color = "#22C55E" if score >= 70 else "#3B82F6" if score >= 50 else "#F59E0B"

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🎯 {lead.get('title', 'New Lead')}"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Type:*\n{lead.get('lead_type', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*Score:*\n{score}/100"},
                        {"type": "mrkdwn", "text": f"*Phone:*\n{lead.get('phone') or 'N/A'}"},
                        {"type": "mrkdwn", "text": f"*Category:*\n{lead.get('category') or 'N/A'}"},
                    ]
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"📍 *Address:* {lead.get('address') or 'N/A'}"}
                },
                {
                    "type": "actions",
                    "elements": [{
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View on Maps"},
                        "url": lead.get("link", "#"),
                    }]
                } if lead.get("link") else {"type": "divider"}
            ]
        }]
    }
    return _post_json(url, payload, "Slack")


def send_slack_summary(product: str, region: str, total: int,
                       score_summary: dict, webhook_url: str = None) -> dict:
    """Send a search summary to Slack."""
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return {"success": False, "error": "SLACK_WEBHOOK_URL not set."}

    text = (
        f"✅ *Lead Search Complete*\n"
        f"Product: *{product}* | Region: *{region}*\n"
        f"Leads found: *{total}* | "
        f"Max score: *{score_summary.get('max', 0)}* | "
        f"Avg: *{score_summary.get('avg', 0)}*"
    )
    return _post_json(url, {"text": text}, "Slack")


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

def send_discord_message(content: str, webhook_url: str = None) -> dict:
    """Send a plain text message to Discord."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return {"success": False, "error": "DISCORD_WEBHOOK_URL not set."}
    return _post_json(url, {"content": content}, "Discord")


def send_discord_lead(lead: dict, webhook_url: str = None) -> dict:
    """Send a rich Discord embed lead card."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return {"success": False, "error": "DISCORD_WEBHOOK_URL not set."}

    score = lead.get("score", 0)
    color = 0x22C55E if score >= 70 else 0x3B82F6 if score >= 50 else 0xF59E0B

    embed = {
        "title":       f"🎯 {lead.get('title', 'New Lead')}",
        "color":       color,
        "fields": [
            {"name": "Lead Type",  "value": lead.get("lead_type", "N/A"),     "inline": True},
            {"name": "Score",      "value": f"{score}/100",                    "inline": True},
            {"name": "Phone",      "value": lead.get("phone") or "N/A",       "inline": True},
            {"name": "Category",   "value": lead.get("category") or "N/A",    "inline": True},
            {"name": "Address",    "value": lead.get("address") or "N/A",     "inline": False},
        ],
        "footer": {"text": f"Source: {lead.get('source', 'Lead Gen CRM')}"},
    }

    if lead.get("link"):
        embed["url"] = lead["link"]

    return _post_json(url, {"embeds": [embed]}, "Discord")


# ---------------------------------------------------------------------------
# Send to BOTH Slack and Discord simultaneously
# ---------------------------------------------------------------------------

def notify_all_channels(lead: dict) -> dict:
    """Send lead notification to both Slack and Discord."""
    results = {}

    if os.getenv("SLACK_WEBHOOK_URL"):
        results["slack"] = send_slack_lead(lead)
    else:
        results["slack"] = {"skipped": True, "reason": "SLACK_WEBHOOK_URL not configured"}

    if os.getenv("DISCORD_WEBHOOK_URL"):
        results["discord"] = send_discord_lead(lead)
    else:
        results["discord"] = {"skipped": True, "reason": "DISCORD_WEBHOOK_URL not configured"}

    return results
