"""
scoring.py  —  Generic Lead Scoring & Qualification Engine.

Supports:
1. Generic qualification factor scoring with configurable weights (DEFAULT_CRITERIA)
2. Evidence and missing information extraction
3. Backward-compatible legacy completeness scoring for scatterplot generation
"""

import hashlib
import logging
from typing import Dict, Any, List

logger = logging.getLogger("lead_gen.scoring")

# ---------------------------------------------------------------------------
# Default Generic Qualification Criteria
# ---------------------------------------------------------------------------
DEFAULT_CRITERIA = {
    "business_relevance": 25,
    "customer_fit": 25,
    "purchase_intent_evidence": 20,
    "location_match": 10,
    "contact_quality": 10,
    "business_activity": 10,
}

# ---------------------------------------------------------------------------
# Generic Scoring Engine
# ---------------------------------------------------------------------------
def score_lead(lead: dict, criteria=None, product_name: str = ""):
    """
    Score a lead using generic qualification factors when criteria is a dict,
    or using the keyword/completeness formula when criteria is a product_name string.
    """
    if isinstance(criteria, dict):
        score = 0
        reasons = []

        for factor, weight in criteria.items():
            # Each factor is supplied by your
            # qualification process, not hardcoded
            # to a specific industry.
            value = lead.get("qualification", {}).get(factor)

            if value is None:
                continue

            if value is True:
                score += weight
                reasons.append(f"{factor}: matched")
            elif isinstance(value, (int, float)):
                score += weight * max(0, min(1, value))
                reasons.append(f"{factor}: partially matched")

        score = round(max(0, min(100, score)))

        if score >= 80:
            priority = "High"
        elif score >= 60:
            priority = "Medium"
        else:
            priority = "Low"

        return {
            "lead_score": score,
            "priority": priority,
            "qualification_reasons": reasons,
        }

    # If called with legacy signature: score_lead(lead, product_name)
    p_name = criteria if isinstance(criteria, str) else product_name
    return _legacy_score_lead(lead, p_name)


# ---------------------------------------------------------------------------
# Lead Qualification Engine (Produces Evidence, Intent & Recommended Action)
# ---------------------------------------------------------------------------
def qualify_lead(lead: dict, context: dict = None, criteria: dict = None) -> dict:
    """
    Evaluates a lead against search parameters (product/service, industry,
    target customer types, location, customer goal) and computes qualification
    factors, evidence, missing information, purchase intent, and recommended action.
    """
    context = context or {}
    criteria = criteria or DEFAULT_CRITERIA

    product_or_service = context.get("product_or_service") or context.get("product_name") or ""
    industry = context.get("industry") or ""
    target_customer_types = context.get("target_customer_types") or [
        "distributor", "wholesaler", "retailer", "corporate buyer"
    ]
    location = context.get("location") or context.get("region") or ""
    customer_goal = context.get("customer_goal") or "Sell products"
    search_preferences = context.get("search_preferences") or {}

    # Extract lead text corpus for semantic matching
    title = lead.get("business_name") or lead.get("title") or "Example Business"
    category = lead.get("category") or lead.get("business_type") or lead.get("lead_type") or ""
    snippet = lead.get("snippet") or lead.get("description") or ""
    address = lead.get("address") or ""
    phone = lead.get("phone") or ""
    link = lead.get("link") or lead.get("website") or ""

    full_text = f"{title} {category} {snippet} {address}".lower()

    # If lead already contains pre-computed qualification factors, use them directly
    if "qualification" in lead and isinstance(lead["qualification"], dict) and lead["qualification"]:
        lead_qualification = lead["qualification"]
        relevance_val = lead_qualification.get("business_relevance", 0.5)
        customer_fit_val = lead_qualification.get("customer_fit", 0.5)
        intent_val = lead_qualification.get("purchase_intent_evidence", 0.0)
        location_val = lead_qualification.get("location_match", 0.5)
        contact_val = lead_qualification.get("contact_quality", 0.5)
        activity_val = lead_qualification.get("business_activity", 0.5)
        matched_customer_type = lead.get("business_type") or category or "Commercial Business"
    else:
        # 1. Business Relevance (Weight 25)
        relevance_val = 0.2
        prod_words = [w.lower() for w in product_or_service.split() if len(w) > 2]
        ind_words = [w.lower() for w in industry.split() if len(w) > 2]

        prod_match_count = sum(1 for w in prod_words if w in full_text)
        ind_match_count = sum(1 for w in ind_words if w in full_text)

        if prod_words and prod_match_count >= max(1, len(prod_words) // 2):
            relevance_val = True  # Exact/strong product match
        elif ind_words and ind_match_count > 0:
            relevance_val = True  # Strong industry match
        elif search_preferences.get("include_related_businesses", True) and (prod_match_count > 0 or ind_match_count > 0):
            relevance_val = 0.6
        else:
            relevance_val = 0.3

        # 2. Customer Fit (Weight 25)
        customer_fit_val = 0.3
        matched_customer_type = None
        for ct in target_customer_types:
            ct_clean = ct.lower().strip()
            if ct_clean in full_text:
                customer_fit_val = True
                matched_customer_type = ct.title()
                break

        if not matched_customer_type:
            common_trade_terms = ["distributor", "wholesaler", "dealer", "trader", "supplier", "reseller", "retailer", "buyer"]
            for term in common_trade_terms:
                if term in full_text:
                    customer_fit_val = 0.8
                    matched_customer_type = term.title()
                    break

        if not matched_customer_type:
            matched_customer_type = category or "Business"

        # 3. Purchase Intent Evidence (Weight 20)
        # In B2B lead discovery, explicit purchase intent is unknown until qualified/contacted
        # unless an explicit RFQ / procurement notice is present
        intent_keywords = ["rfq", "purchase order", "procurement tender", "looking to buy", "requirement notice"]
        if any(k in full_text for k in intent_keywords):
            intent_val = True
            purchase_intent = "Confirmed / High"
        elif lead.get("purchase_intent") and lead.get("purchase_intent") != "Unknown":
            intent_val = 0.7
            purchase_intent = lead.get("purchase_intent")
        else:
            intent_val = 0.1
            purchase_intent = "Unknown"

        # 4. Location Match (Weight 10)
        location_val = 0.3
        loc_tokens = [w.lower() for w in location.replace(",", " ").split() if len(w) > 2]
        if loc_tokens:
            loc_matches = sum(1 for w in loc_tokens if w in full_text)
            if loc_matches >= 1:
                location_val = True
            else:
                location_val = 0.4
        else:
            location_val = True

        # 5. Contact Quality (Weight 10)
        contact_val = 0.0
        if phone and link:
            contact_val = True
        elif phone or link:
            contact_val = 0.6
        elif address:
            contact_val = 0.3

        # 6. Business Activity (Weight 10)
        activity_val = 0.5
        if link or lead.get("rating") or lead.get("user_ratings_total"):
            activity_val = True
        elif phone:
            activity_val = 0.75

        # Store computed qualification factors into lead
        lead["qualification"] = {
            "business_relevance": relevance_val,
            "customer_fit": customer_fit_val,
            "purchase_intent_evidence": intent_val,
            "location_match": location_val,
            "contact_quality": contact_val,
            "business_activity": activity_val,
        }

    # Purchase Intent resolution
    if "purchase_intent" not in locals():
        purchase_intent = lead.get("purchase_intent") or "Unknown"

    # Determine structured business_type (e.g. "IT Distributor")
    cat_lower = (category or "").lower()
    if any(ct.lower() in cat_lower for ct in ["distributor", "wholesaler", "retailer", "buyer"]):
        business_type = category.title()
    elif industry and matched_customer_type:
        ind_label = "IT" if industry.lower().startswith("it") else industry.split()[0].title()
        if ind_label.lower() in matched_customer_type.lower():
            business_type = matched_customer_type.title()
        else:
            business_type = f"{ind_label} {matched_customer_type}".title()
    elif matched_customer_type:
        business_type = matched_customer_type.title()
    else:
        business_type = category or "Commercial Business"

    if business_type.lower().startswith("it "):
        business_type = "IT " + business_type[3:]

    # Run generic scoring engine
    scored = score_lead(lead, criteria)
    lead_score = scored["lead_score"]
    priority = scored["priority"]
    qualification_reasons = scored["qualification_reasons"]

    # Assemble Evidence list matching user specification
    evidence = []
    if relevance_val in (True, 1.0) or (isinstance(relevance_val, (int, float)) and relevance_val >= 0.7):
        if industry:
            trade_role = matched_customer_type.lower() if matched_customer_type else "distribution"
            if "distribut" in trade_role:
                trade_suffix = "distribution"
            elif "wholesale" in trade_role:
                trade_suffix = "wholesale"
            elif "retail" in trade_role:
                trade_suffix = "retail"
            else:
                trade_suffix = trade_role
            evidence.append(f"Business website lists {industry} {trade_suffix}")
        elif product_or_service:
            evidence.append(f"Business website lists {product_or_service} distribution")
        else:
            evidence.append("Business profile matches targeted industry")

    if location_val in (True, 1.0) or (isinstance(location_val, (int, float)) and location_val >= 0.7):
        evidence.append("Business operates in the requested region")

    # Assemble Missing Information
    missing_info = []
    if purchase_intent == "Unknown":
        missing_info.append("Purchasing requirements not confirmed")
    if search_preferences.get("require_verified_contact") and not (lead.get("scraped_email") or lead.get("email")):
        missing_info.append("Direct procurement decision maker email not verified")
    if not phone and not search_preferences.get("require_verified_contact") is False:
        missing_info.append("Direct contact phone number missing")

    # Qualification Status
    if lead_score < 50:
        qualification_status = "Unqualified"
    elif purchase_intent == "Unknown":
        qualification_status = "Potential Lead"
    else:
        qualification_status = "Qualified Lead"

    # Recommended Action
    if lead_score >= 60:
        recommended_action = "Contact business to qualify demand"
    else:
        recommended_action = "Enrich business profile and verify contact before outreach"

    # Build response with exact user format first, followed by metadata
    result = {
        "business_name": title,
        "business_type": business_type,
        "lead_score": lead_score,
        "priority": priority,
        "qualification_status": qualification_status,
        "evidence": evidence,
        "missing_information": missing_info,
        "purchase_intent": purchase_intent,
        "recommended_action": recommended_action,
        # Helper and metadata fields for downstream CRM/UI support
        "phone": phone,
        "address": address,
        "link": link,
        "category": category,
        "source": lead.get("source", "Search"),
        "matched_query": lead.get("matched_query", ""),
        "score": lead_score,
        "title": title,
        "qualification_reasons": qualification_reasons,
        "qualification": lead["qualification"],
    }

    return result


# ---------------------------------------------------------------------------
# Legacy Scoring & Scatterplot Support (Preserved for compatibility)
# ---------------------------------------------------------------------------
_LEAD_TYPE_BONUS = {
    "Active Buyer":                 15,
    "Distributor / Wholesaler":     12,
    "Manufacturer (Potential OEM Buyer)": 10,
    "Decision Maker Profile":        8,
    "Business Directory Listing":    3,
    "Potential Lead":                0,
}

_BUYER_KEYWORDS = [
    "buyer", "importer", "wholesaler", "distributor",
    "trader", "dealer", "supplier", "procurement",
]

def _legacy_score_lead(lead: dict, product_name: str = "") -> int:
    score = 0
    if lead.get("phone"):
        score += 20
    if lead.get("link"):
        score += 15
    if lead.get("address"):
        score += 10
    if lead.get("category"):
        score += 10

    lead_type = lead.get("lead_type", "Potential Lead")
    score += _LEAD_TYPE_BONUS.get(lead_type, 0)

    title_text = (lead.get("title", "") + " " + lead.get("category", "")).lower()
    product_words = [w.lower() for w in product_name.split() if len(w) > 2]
    if product_words:
        matched = sum(1 for w in product_words if w in title_text)
        relevance_score = int((matched / len(product_words)) * 15)
        score += relevance_score

    matched_query = lead.get("matched_query", "").lower()
    if any(kw in matched_query for kw in _BUYER_KEYWORDS):
        score += 5

    return min(max(score, 0), 100)


def _location_to_x(address: str, fallback_index: int) -> float:
    if not address:
        return float(fallback_index)
    digest = int(hashlib.md5(address.encode()).hexdigest(), 16)
    return round((digest % 10_000) / 100.0, 2)


def build_scatterplot_data(leads: list, product_name: str = "") -> list:
    points = []
    for i, lead in enumerate(leads):
        score = _legacy_score_lead(lead, product_name)
        lng = lead.get("longitude")
        x_val = round(float(lng), 6) if lng is not None else _location_to_x(lead.get("address", ""), i)

        points.append({
            "x":             x_val,
            "y":             score,
            "title":         lead.get("title", ""),
            "address":       lead.get("address", ""),
            "lead_type":     lead.get("lead_type", "Potential Lead"),
            "score":         score,
            "phone":         lead.get("phone", ""),
            "source":        lead.get("source", ""),
            "matched_query": lead.get("matched_query", ""),
        })

    points.sort(key=lambda p: p["score"], reverse=True)
    return points


def attach_scores(leads: list, product_name: str = "") -> list:
    for lead in leads:
        lead["score"] = _legacy_score_lead(lead, product_name)
    leads.sort(key=lambda l: l["score"], reverse=True)
    return leads
