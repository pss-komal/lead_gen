"""
gemini_service.py  —  Google Gemini AI integration (FREE tier).

Free limits: 15 requests/min | 1 million tokens/month | No card needed
API Key    : https://aistudio.google.com/app/apikey  (get free key instantly)

Use cases:
  - Generate personalized cold outreach messages per lead
  - AI-based lead quality analysis
  - Batch lead insights summary
"""

import os
import logging
import requests

logger = logging.getLogger("lead_gen.gemini")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


def _call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini and return the text response."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "ERROR: GEMINI_API_KEY not set in .env"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 500,
        },
    }

    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": api_key},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        logger.info("Gemini response received (%d chars)", len(text))
        return text.strip()
    except Exception as exc:
        logger.error("Gemini API error: %s", exc)
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Feature 1 — Generate personalized outreach message for a lead
# ---------------------------------------------------------------------------

def generate_outreach_message(lead: dict, product_name: str, sender_name: str = "Sales Team") -> dict:
    """
    Generate a personalized WhatsApp/email outreach message for a specific lead.

    Parameters
    ----------
    lead         : dict  lead data (title, category, address, lead_type, phone)
    product_name : str   your product name
    sender_name  : str   your name / company name
    """
    prompt = f"""
You are an expert B2B sales copywriter. Write a short, personalized WhatsApp outreach message.

Lead Details:
- Business Name : {lead.get('title', 'Unknown')}
- Business Type : {lead.get('category', 'Unknown')}
- Lead Type     : {lead.get('lead_type', 'Potential Lead')}
- Location      : {lead.get('address', 'Unknown')}
- Product       : {product_name}
- Sender        : {sender_name}

Rules:
1. Max 4 sentences
2. Mention their business name and location naturally
3. Explain briefly how {product_name} benefits THEIR specific business type
4. End with a soft call to action (e.g. "Would love to connect!")
5. Friendly and professional tone — NOT spammy
6. Write in English only

Write ONLY the message, no explanation.
"""
    message = _call_gemini(prompt)
    return {
        "lead_title":  lead.get("title"),
        "product":     product_name,
        "ai_message":  message,
        "channel":     "WhatsApp / Email",
    }


# ---------------------------------------------------------------------------
# Feature 2 — AI lead quality analysis
# ---------------------------------------------------------------------------

def analyze_lead(lead: dict, product_name: str) -> dict:
    """
    Use Gemini to give an intelligent, contextual quality assessment of a lead.
    Returns: fit_score, reasoning, recommended_action
    """
    prompt = f"""
You are a B2B sales analyst. Evaluate this lead for the product "{product_name}".

Lead:
- Business: {lead.get('title')}
- Type    : {lead.get('lead_type')}
- Category: {lead.get('category')}
- Address : {lead.get('address')}
- Phone   : {'Yes' if lead.get('phone') else 'No'}
- Website : {'Yes' if lead.get('link') else 'No'}

Respond in this exact format:
FIT_SCORE: [number 1-100]
REASONING: [1-2 sentences explaining why this lead is or isn't a good fit]
ACTION: [one specific recommended sales action e.g. "Call immediately with bulk pricing offer"]
"""
    raw = _call_gemini(prompt)

    # Parse the structured response
    result = {"raw": raw, "lead_title": lead.get("title")}
    for line in raw.splitlines():
        if line.startswith("FIT_SCORE:"):
            try:
                result["ai_fit_score"] = int(line.split(":")[1].strip())
            except ValueError:
                result["ai_fit_score"] = None
        elif line.startswith("REASONING:"):
            result["ai_reasoning"] = line.split(":", 1)[1].strip()
        elif line.startswith("ACTION:"):
            result["ai_recommended_action"] = line.split(":", 1)[1].strip()

    return result


# ---------------------------------------------------------------------------
# Feature 3 — Batch summary of all leads
# ---------------------------------------------------------------------------

def summarize_leads_batch(leads: list, product_name: str, region: str) -> dict:
    """
    Analyze the full batch of leads and give strategic insights.
    """
    lead_list = "\n".join(
        f"- {l.get('title')} ({l.get('category')}) | Score: {l.get('score', 0)} | "
        f"Phone: {'Yes' if l.get('phone') else 'No'}"
        for l in leads[:15]   # limit to 15 to stay within token limit
    )

    prompt = f"""
You are a B2B sales strategist. Analyze this batch of leads for "{product_name}" in "{region}".

Leads Found:
{lead_list}

Give a strategic analysis in this format:
SUMMARY: [2 sentences about overall lead quality]
TOP_LEADS: [names of the 2-3 best leads to contact first]
STRATEGY: [1 recommended outreach strategy for this region/product]
RED_FLAGS: [any concerns or low-quality patterns in the leads]
"""
    raw = _call_gemini(prompt)
    return {
        "product_name": product_name,
        "region":       region,
        "total_leads":  len(leads),
        "ai_analysis":  raw,
    }
