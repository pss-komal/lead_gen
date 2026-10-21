import os
import logging
import requests

from .scoring import attach_scores, build_scatterplot_data

# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("lead_gen.apify_service")


# ---------------------------------------------------------------------------
# Query builder  (same logic as SerpAPI service — reusable pattern)
# ---------------------------------------------------------------------------

def build_maps_queries(product_name: str, region: str, description: str) -> list:
    """
    Craft Google Maps search queries to find local businesses that are
    likely buyers / users of the product in the specified region.
    """
    return [
        f"{product_name} buyer OR importer OR wholesaler OR distributor {region}",
        f"{product_name} {description} {region}",
        f"{product_name} trader OR supplier OR dealer {region}",
    ]


# ---------------------------------------------------------------------------
# Lead classifier  (same heuristic as SerpAPI service)
# ---------------------------------------------------------------------------

def classify_lead(title: str, snippet: str, category: str = "") -> str:
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


# ---------------------------------------------------------------------------
# Core Apify function
# ---------------------------------------------------------------------------

def search_apify(product_name: str, region: str, description: str, limit: int):
    """
    Search using Apify's Google Maps Scraper actor to find local businesses
    that are likely buyers of the given product in the specified region.

    Actor used: compass/crawler-google-places
    Docs     : https://apify.com/compass/crawler-google-places

    Each lead in the response includes:
        lead_type, title, link, phone, address, category, status,
        snippet, source, matched_query
    """
    logger.info("=" * 60)
    logger.info("NEW LEAD SEARCH STARTED  [engine: apify/google-maps-scraper]")
    logger.info("  Product    : %s", product_name)
    logger.info("  Region     : %s", region)
    logger.info("  Description: %s", description)
    logger.info("  Limit      : %d", limit)
    logger.info("=" * 60)

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        logger.error("APIFY_API_TOKEN is not set in environment variables!")
        return {
            "product_name":      product_name,
            "region":            region,
            "description":       description,
            "total_leads_found": 0,
            "leads":             [],
            "error":             "APIFY_API_TOKEN environment variable is not set.",
        }

    queries = build_maps_queries(product_name, region, description)
    logger.info("Built %d Maps queries.", len(queries))

    seen_titles = set()
    all_leads   = []

    # Apify actor endpoint — synchronous run (waits for result)
    # Actor ID uses ~ as separator in the REST API URL (not /)
    actor_id = "compass~crawler-google-places"
    run_url  = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    for idx, query in enumerate(queries, start=1):
        if len(all_leads) >= limit:
            logger.info("Lead limit (%d) reached — stopping early.", limit)
            break

        logger.info("[Query %d/%d] Firing: %s", idx, len(queries), query)

        # Apify actor input — compass/crawler-google-places schema
        actor_input = {
            "searchStringsArray": [query],
            "maxCrawledPlacesPerSearch": limit,   # upper bound per query
            "language": "en",
            "includeHistogram": False,
            "includeOpeningHours": False,
            "includePeopleAlsoSearchFor": False,
        }

        try:
            response = requests.post(
                run_url,
                params={"token": api_token, "timeout": 120},
                json=actor_input,
                timeout=180,          # HTTP timeout (seconds)
            )
            logger.info(
                "[Query %d/%d] Apify HTTP status: %d",
                idx, len(queries), response.status_code,
            )
            # Apify run-sync-get-dataset-items returns 201 on success
            if response.status_code not in (200, 201):
                logger.error(
                    "[Query %d/%d] Apify non-2xx response — body: %s",
                    idx, len(queries), response.text[:500],
                )
                continue
            items = response.json()   # list of place objects
            if not isinstance(items, list):
                logger.error(
                    "[Query %d/%d] Unexpected Apify response type: %s — body: %s",
                    idx, len(queries), type(items).__name__, str(items)[:300],
                )
                continue
        except requests.exceptions.HTTPError as exc:
            logger.error(
                "[Query %d/%d] Apify HTTP error: %s — body: %s",
                idx, len(queries), exc, exc.response.text[:500] if exc.response else "",
            )
            continue
        except requests.exceptions.Timeout:
            logger.error("[Query %d/%d] Apify request timed out (180s)", idx, len(queries))
            continue
        except Exception as exc:
            logger.error("[Query %d/%d] Apify call failed: %s", idx, len(queries), exc)
            continue

        logger.info("[Query %d/%d] Received %d Apify results.", idx, len(queries), len(items))

        added_this_query    = 0
        skipped_duplicates  = 0

        for item in items:
            if len(all_leads) >= limit:
                logger.info("[Query %d/%d] Lead limit hit mid-results — stopping.", idx, len(queries))
                break

            # --- Extract fields from compass/crawler-google-places output ---
            title    = item.get("title", "")
            phone    = item.get("phone") or item.get("phoneUnformatted") or ""
            address  = item.get("address") or item.get("street") or ""
            # categoryName is a top-level string in the real actor output
            category = item.get("categoryName") or ""
            website   = item.get("website") or ""
            place_url = item.get("url") or ""   # Google Maps place URL
            link      = website or place_url or ""

            # Real GPS coordinates — Apify provides these natively
            location  = item.get("location") or {}
            latitude  = location.get("lat")
            longitude = location.get("lng")

            # Deduplicate by normalised company name
            name_key = title.lower().strip()
            if not name_key or name_key in seen_titles:
                skipped_duplicates += 1
                continue
            seen_titles.add(name_key)

            lead_type = classify_lead(title, address or "", category or "")

            all_leads.append(
                {
                    "lead_type":     lead_type,
                    "title":         title,
                    "link":          link,
                    "phone":         phone,
                    "address":       address,
                    "category":      category,
                    "status":        "new",
                    "snippet":       address or "",
                    "source":        "Google Maps (Apify)",
                    "matched_query": query,
                    # GPS coords for scatterplot (may be None if not returned)
                    "latitude":      latitude,
                    "longitude":     longitude,
                }
            )
            added_this_query += 1
            logger.debug(
                "  + Lead [%s] | phone=%s | addr=%s | cat=%s",
                lead_type, phone, (address or "")[:40], category,
            )

        logger.info(
            "[Query %d/%d] Added %d leads | Skipped %d duplicates | Total so far: %d",
            idx, len(queries), added_this_query, skipped_duplicates, len(all_leads),
        )

    logger.info("-" * 60)
    logger.info("APIFY SEARCH COMPLETE — Total leads found: %d", len(all_leads))
    logger.info("-" * 60)

    # --- Score every lead and build scatterplot data ---
    scored_leads    = attach_scores(all_leads, product_name)
    scatterplot     = build_scatterplot_data(scored_leads, product_name)

    # Score summary for quick frontend use
    scores          = [l["score"] for l in scored_leads]
    score_summary   = {
        "max":  max(scores) if scores else 0,
        "min":  min(scores) if scores else 0,
        "avg":  round(sum(scores) / len(scores), 1) if scores else 0,
    }

    return {
        "product_name":      product_name,
        "region":            region,
        "description":       description,
        "total_leads_found": len(scored_leads),
        "score_summary":     score_summary,
        "leads":             scored_leads,
        "scatterplot_data":  scatterplot,
    }
