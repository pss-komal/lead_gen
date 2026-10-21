import os
import logging
from serpapi import GoogleSearch

from .scoring import attach_scores, build_scatterplot_data, qualify_lead

# ---------------------------------------------------------------------------
# Logger setup  —  logs appear on the terminal (uvicorn stdout)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lead_gen.serp_service")


def build_maps_queries(product_name: str, region: str, description: str, context: dict = None) -> list:
    """
    Craft Google Maps search queries to find local businesses that are
    likely buyers / users of the product in the specified region.
    Maps results come with phone, address, and category — ready-made lead data.
    """
    queries = []
    if context and context.get("target_customer_types"):
        for ct in context.get("target_customer_types")[:3]:
            queries.append(f"{product_name} {ct} {region}")

    queries.extend([
        # Distributors / wholesalers / importers
        f"{product_name} buyer OR importer OR wholesaler OR distributor {region}",

        # Companies that use the product (potential OEM / industrial buyers)
        f"{product_name} {description} {region}",

        # Procurement / trading companies
        f"{product_name} trader OR supplier OR dealer {region}",
    ])
    return queries


def classify_lead(title: str, snippet: str, category: str = "") -> str:
    """
    Heuristically classify the type of lead.
    Now also uses the Google Maps `category` (type) field for better accuracy.
    """
    text = (title + " " + snippet + " " + (category or "")).lower()

    if any(kw in text for kw in ["buy", "purchase", "order", "procurement", "rfq", "sourcing", "import"]):
        return "Active Buyer"
    if any(kw in text for kw in ["distributor", "wholesaler", "reseller", "dealer", "trader"]):
        return "Distributor / Wholesaler"
    if any(kw in text for kw in ["manufacturer", "factory", "producer", "oem"]):
        return "Manufacturer (Potential OEM Buyer)"
    if any(kw in text for kw in ["linkedin", "profile", "manager", "director", "executive"]):
        return "Decision Maker Profile"
    if any(kw in text for kw in ["directory", "listing", "yellow pages", "bizbuyer"]):
        return "Business Directory Listing"
    return "Potential Lead"


def search_serpapi(product_name: str, region: str, description: str, limit: int, context: dict = None, criteria: dict = None):
    """
    Search SerpAPI using Google Maps engine to find local businesses that are
    likely buyers of the given product in the specified region.

    Google Maps results natively include:
        phone, address, category (type), rating, website
    — which makes them far more lead-ready than generic organic results.
    """
    logger.info("=" * 60)
    logger.info("NEW LEAD SEARCH STARTED  [engine: google_maps]")
    logger.info("  Product    : %s", product_name)
    logger.info("  Region     : %s", region)
    logger.info("  Description: %s", description)
    logger.info("  Limit      : %d", limit)
    logger.info("=" * 60)

    context = context or {
        "product_or_service": product_name,
        "location": region,
        "industry": description,
        "customer_goal": "Sell products",
    }

    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        logger.error("SERPAPI_API_KEY is not set in environment variables!")
        return {
            "product_name":      product_name,
            "product_or_service": context.get("product_or_service", product_name),
            "region":            region,
            "location":          context.get("location", region),
            "industry":          context.get("industry", description),
            "description":       description,
            "total_leads_found": 0,
            "leads":             [],
            "scatterplot_data":  [],
            "error":             "SERPAPI_API_KEY environment variable is not set.",
        }

    queries = build_maps_queries(product_name, region, description, context)
    logger.info("Built %d Maps queries.", len(queries))

    seen_titles = set()   # Maps results don't always have unique links; dedupe by name
    all_leads = []

    for idx, query in enumerate(queries, start=1):
        if len(all_leads) >= limit:
            logger.info("Lead limit (%d) reached — stopping early.", limit)
            break

        logger.info("[Query %d/%d] Firing: %s", idx, len(queries), query)

        params = {
            "engine":  "google_maps",
            "q":       query,
            "api_key": api_key,
            "type":    "search",
            "hl":      "en",
        }

        try:
            search = GoogleSearch(params)
            results = search.get_dict()
        except Exception as exc:
            logger.error("SerpAPI call failed for query %d: %s", idx, exc)
            continue

        local_results = results.get("local_results", [])
        logger.info("[Query %d/%d] Received %d Maps results.", idx, len(queries), len(local_results))

        added_this_query = 0
        skipped_duplicates = 0

        for result in local_results:
            if len(all_leads) >= limit:
                logger.info("[Query %d/%d] Lead limit hit mid-results — stopping.", idx, len(queries))
                break

            # --- Extract all available fields from Maps result ---
            title    = result.get("title", "")
            phone    = result.get("phone")          # e.g. "+91 98765 43210"
            address  = result.get("address")        # e.g. "Andheri East, Mumbai"
            category = result.get("type")           # e.g. "Valve supplier"
            website  = result.get("website")        # company website URL
            link     = website or result.get("place_id_search", "")

            # Deduplicate by normalised company name
            name_key = title.lower().strip()
            if not name_key or name_key in seen_titles:
                skipped_duplicates += 1
                continue
            seen_titles.add(name_key)

            # Classify lead type using title + address + Maps category
            lead_type = classify_lead(title, address or "", category or "")

            all_leads.append(
                {
                    "lead_type":     lead_type,
                    "title":         title,
                    "business_name": title,
                    "link":          link,
                    "phone":         phone,
                    "address":       address,
                    "category":      category,
                    "status":        "new",
                    "snippet":       address or "",   # address doubles as a useful snippet
                    "source":        "Google Maps",
                    "matched_query": query,
                }
            )
            added_this_query += 1

        logger.info(
            "[Query %d/%d] Added %d leads | Skipped %d duplicates | Total so far: %d",
            idx, len(queries), added_this_query, skipped_duplicates, len(all_leads),
        )

    logger.info("-" * 60)
    logger.info("SEARCH COMPLETE — Total leads found: %d", len(all_leads))
    logger.info("-" * 60)

    # --- Qualify every lead and build scatterplot data ---
    qualified_leads = [qualify_lead(l, context, criteria) for l in all_leads]
    qualified_leads.sort(key=lambda l: l["lead_score"], reverse=True)

    scatterplot   = build_scatterplot_data(qualified_leads, product_name)
    scores        = [l["lead_score"] for l in qualified_leads]
    score_summary = {
        "max":  max(scores) if scores else 0,
        "min":  min(scores) if scores else 0,
        "avg":  round(sum(scores) / len(scores), 1) if scores else 0,
    }

    return {
        "product_name":      product_name,
        "product_or_service": context.get("product_or_service", product_name),
        "region":            region,
        "location":          context.get("location", region),
        "industry":          context.get("industry", description),
        "description":       description,
        "total_leads_found": len(qualified_leads),
        "score_summary":     score_summary,
        "leads":             qualified_leads,
        "scatterplot_data":  scatterplot,
    }