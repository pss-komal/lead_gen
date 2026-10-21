"""
scoring.py  —  Lead quality scoring and scatterplot data generation.

Score formula (0–100):
  - Has phone number     : +20 pts
  - Has website          : +15 pts
  - Has address          : +10 pts
  - Has category         : +10 pts
  - Lead type bonus      : 0–15 pts  (Active Buyer = 15, Potential Lead = 0)
  - Keyword relevance    : 0–15 pts  (product name found in title/category)
  - Query match strength : 0– 5 pts  (buyer/trader/distributor in matched query)

Scatterplot point:
  {x, y, title, address, lead_type, score, source, matched_query}
  where  y = score  and  x = longitude (if available) or location_index
"""

import hashlib
import logging

logger = logging.getLogger("lead_gen.scoring")

# ---------------------------------------------------------------------------
# Lead type score bonus table
# ---------------------------------------------------------------------------
_LEAD_TYPE_BONUS = {
    "Active Buyer":                 15,
    "Distributor / Wholesaler":     12,
    "Manufacturer (Potential OEM Buyer)": 10,
    "Decision Maker Profile":        8,
    "Business Directory Listing":    3,
    "Potential Lead":                0,
}

# ---------------------------------------------------------------------------
# Keywords that indicate a strong buyer signal
# ---------------------------------------------------------------------------
_BUYER_KEYWORDS = [
    "buyer", "importer", "wholesaler", "distributor",
    "trader", "dealer", "supplier", "procurement",
]


def score_lead(lead: dict, product_name: str = "") -> int:
    """
    Compute a quality score (0–100) for a single lead dict.

    Parameters
    ----------
    lead         : dict with keys title, phone, address, website/link, category,
                   lead_type, matched_query
    product_name : the product being searched (used for keyword relevance)

    Returns
    -------
    int  score in range [0, 100]
    """
    score = 0

    # --- Completeness signals ---
    if lead.get("phone"):
        score += 20
    if lead.get("link"):
        score += 15
    if lead.get("address"):
        score += 10
    if lead.get("category"):
        score += 10

    # --- Lead type bonus ---
    lead_type = lead.get("lead_type", "Potential Lead")
    score += _LEAD_TYPE_BONUS.get(lead_type, 0)

    # --- Keyword relevance (title + category vs product name) ---
    title_text    = (lead.get("title", "") + " " + lead.get("category", "")).lower()
    product_words = [w.lower() for w in product_name.split() if len(w) > 2]
    if product_words:
        matched = sum(1 for w in product_words if w in title_text)
        relevance_score = int((matched / len(product_words)) * 15)
        score += relevance_score

    # --- Query match strength (buyer intent in the matched query) ---
    matched_query = lead.get("matched_query", "").lower()
    if any(kw in matched_query for kw in _BUYER_KEYWORDS):
        score += 5

    # Clamp to [0, 100]
    return min(max(score, 0), 100)


# ---------------------------------------------------------------------------
# Scatterplot helpers
# ---------------------------------------------------------------------------

def _location_to_x(address: str, fallback_index: int) -> float:
    """
    Deterministic X-axis value for SerpAPI leads (no real coordinates).
    Uses a hash of the address to spread points consistently.
    Falls back to fallback_index if no address.
    """
    if not address:
        return float(fallback_index)
    digest = int(hashlib.md5(address.encode()).hexdigest(), 16)
    # Map hash to a 0–100 float range so all points fit a common X scale
    return round((digest % 10_000) / 100.0, 2)


def build_scatterplot_data(leads: list, product_name: str = "") -> list:
    """
    Generate scatterplot-ready data from a list of leads.

    Each point contains:
        x           - longitude if available, else deterministic hash of address
        y           - lead quality score (0–100)
        title       - business name
        address     - full address string
        lead_type   - classified lead type
        score       - same as y (for clarity)
        phone       - contact phone
        source      - 'Google Maps' or 'Google Maps (Apify)'
        matched_query

    Points are sorted by score descending so the best leads appear first.
    """
    points = []

    for i, lead in enumerate(leads):
        score = score_lead(lead, product_name)

        # Use real longitude if Apify provided it, else derive from address hash
        lng = lead.get("longitude")
        x_val = round(float(lng), 6) if lng is not None else _location_to_x(lead.get("address", ""), i)

        points.append(
            {
                "x":            x_val,
                "y":            score,
                "title":        lead.get("title", ""),
                "address":      lead.get("address", ""),
                "lead_type":    lead.get("lead_type", "Potential Lead"),
                "score":        score,
                "phone":        lead.get("phone", ""),
                "source":       lead.get("source", ""),
                "matched_query": lead.get("matched_query", ""),
            }
        )

    # Sort highest score first
    points.sort(key=lambda p: p["score"], reverse=True)

    logger.info(
        "Scatterplot built: %d points | top score: %d | lowest score: %d",
        len(points),
        points[0]["score"] if points else 0,
        points[-1]["score"] if points else 0,
    )

    return points


def attach_scores(leads: list, product_name: str = "") -> list:
    """
    Add a 'score' field to each lead dict in-place and return the list
    sorted by score descending.
    """
    for lead in leads:
        lead["score"] = score_lead(lead, product_name)
    leads.sort(key=lambda l: l["score"], reverse=True)
    return leads
