"""
google_maps_service.py  —  Direct integration with Google Places API (v1).

NO middleman (no SerpAPI, no Apify).
Calls Google's own API directly using your Google Cloud API key.

API used : Google Places API (New) — Text Search
Docs     : https://developers.google.com/maps/documentation/places/web-service/text-search
"""

import os
import logging
import requests

from .scoring import attach_scores, build_scatterplot_data

logger = logging.getLogger("lead_gen.google_maps_service")

# ---------------------------------------------------------------------------
# Google Places API v1 endpoint
# ---------------------------------------------------------------------------
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Fields to request from Google Places API
# (Only pay for what you request — Google bills per field mask)
FIELD_MASK = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.location",
    "places.primaryType",
    "places.types",
    "places.rating",
    "places.googleMapsUri",
    "places.businessStatus",
])


# ---------------------------------------------------------------------------
# Query builder — same pattern as SerpAPI / Apify services
# ---------------------------------------------------------------------------

def build_queries(product_name: str, region: str, description: str) -> list:
    return [
        f"{product_name} buyer OR importer OR wholesaler OR distributor {region}",
        f"{product_name} {description} {region}",
        f"{product_name} trader OR supplier OR dealer {region}",
    ]


# ---------------------------------------------------------------------------
# Lead classifier — same heuristic across all services
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
# Core direct Google Places search function
# ---------------------------------------------------------------------------

def search_google_maps(product_name: str, region: str, description: str, limit: int):
    """
    Search Google Maps directly using the official Google Places API (New).

    Steps:
      1. Build search queries
      2. POST to https://places.googleapis.com/v1/places:searchText
      3. Extract: name, phone, address, website, lat/lng, category
      4. Classify + score leads
      5. Return leads + scatterplot_data

    Requires: GOOGLE_MAPS_API_KEY in .env
    """
    logger.info("=" * 60)
    logger.info("NEW LEAD SEARCH  [engine: Google Places API — DIRECT]")
    logger.info("  Product    : %s", product_name)
    logger.info("  Region     : %s", region)
    logger.info("  Description: %s", description)
    logger.info("  Limit      : %d", limit)
    logger.info("=" * 60)

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.error("GOOGLE_MAPS_API_KEY is not set in environment variables!")
        return {
            "product_name":      product_name,
            "region":            region,
            "description":       description,
            "total_leads_found": 0,
            "leads":             [],
            "scatterplot_data":  [],
            "error":             "GOOGLE_MAPS_API_KEY environment variable is not set.",
        }

    queries    = build_queries(product_name, region, description)
    seen_titles = set()
    all_leads   = []

    headers = {
        "Content-Type":    "application/json",
        "X-Goog-Api-Key":  api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    for idx, query in enumerate(queries, start=1):
        if len(all_leads) >= limit:
            logger.info("Lead limit (%d) reached — stopping early.", limit)
            break

        logger.info("[Query %d/%d] Firing: %s", idx, len(queries), query)

        body = {
            "textQuery":          query,
            "maxResultCount":     min(limit, 20),   # Google max = 20 per request
            "languageCode":       "en",
        }

        try:
            response = requests.post(
                PLACES_TEXT_SEARCH_URL,
                headers=headers,
                json=body,
                timeout=30,
            )
            logger.info("[Query %d/%d] HTTP status: %d", idx, len(queries), response.status_code)

            if response.status_code != 200:
                logger.error(
                    "[Query %d/%d] Google Places API error — body: %s",
                    idx, len(queries), response.text[:500],
                )
                continue

            data   = response.json()
            places = data.get("places", [])

        except requests.exceptions.Timeout:
            logger.error("[Query %d/%d] Request timed out.", idx, len(queries))
            continue
        except Exception as exc:
            logger.error("[Query %d/%d] Request failed: %s", idx, len(queries), exc)
            continue

        logger.info("[Query %d/%d] Received %d places.", idx, len(queries), len(places))

        added_this_query   = 0
        skipped_duplicates = 0

        for place in places:
            if len(all_leads) >= limit:
                break

            # --- Extract fields from Google Places API response ---
            title   = place.get("displayName", {}).get("text", "")
            phone   = (
                place.get("internationalPhoneNumber")
                or place.get("nationalPhoneNumber")
                or ""
            )
            address  = place.get("formattedAddress", "")
            website  = place.get("websiteUri", "")
            maps_url = place.get("googleMapsUri", "")
            link     = website or maps_url or ""

            # Google Places returns primaryType like "electronics_store"
            primary_type = place.get("primaryType", "").replace("_", " ").title()
            types        = [t.replace("_", " ").title() for t in place.get("types", [])]
            category     = primary_type or (types[0] if types else "")

            # GPS coordinates
            location  = place.get("location", {})
            latitude  = location.get("latitude")
            longitude = location.get("longitude")

            rating    = place.get("rating")
            status    = place.get("businessStatus", "OPERATIONAL")

            # Deduplicate by normalised name
            name_key = title.lower().strip()
            if not name_key or name_key in seen_titles:
                skipped_duplicates += 1
                continue
            seen_titles.add(name_key)

            lead_type = classify_lead(title, address, category)

            all_leads.append({
                "lead_type":     lead_type,
                "title":         title,
                "link":          link,
                "phone":         phone,
                "address":       address,
                "category":      category,
                "rating":        rating,
                "status":        "new",
                "business_status": status,
                "snippet":       address,
                "source":        "Google Places API (Direct)",
                "matched_query": query,
                "latitude":      latitude,
                "longitude":     longitude,
            })
            added_this_query += 1

        logger.info(
            "[Query %d/%d] Added %d | Skipped %d duplicates | Total: %d",
            idx, len(queries), added_this_query, skipped_duplicates, len(all_leads),
        )

    logger.info("-" * 60)
    logger.info("GOOGLE PLACES SEARCH COMPLETE — Total: %d leads", len(all_leads))
    logger.info("-" * 60)

    scored_leads  = attach_scores(all_leads, product_name)
    scatterplot   = build_scatterplot_data(scored_leads, product_name)
    scores        = [l["score"] for l in scored_leads]
    score_summary = {
        "max": max(scores) if scores else 0,
        "min": min(scores) if scores else 0,
        "avg": round(sum(scores) / len(scores), 1) if scores else 0,
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
