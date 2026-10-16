import os
import logging
from serpapi import GoogleSearch

# ---------------------------------------------------------------------------
# Logger setup  —  logs appear on the terminal (uvicorn stdout)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lead_gen.serp_service")


def build_buyer_queries(product_name: str, region: str, description: str) -> list:
    """
    Craft multiple buyer-intent search queries so SerpAPI finds
    businesses / people who are likely to BUY the product - i.e., your leads.
    """
    queries = [
        # Businesses actively looking to purchase / source the product
        f'"{product_name}" buyer OR importer OR wholesaler OR distributor in {region}',

        # Companies that use this product in their workflow
        f'companies that use {product_name} in {region} {description}',

        # RFQ / procurement intent
        f'{product_name} RFQ OR "request for quotation" OR procurement {region}',

        # LinkedIn / directory style - decision-maker companies
        f'site:linkedin.com "{product_name}" buyer OR "purchasing manager" {region}',

        # Industry directories that list buyers
        f'{product_name} {description} business directory {region}',
    ]
    return queries


def classify_lead(title: str, snippet: str) -> str:
    """Heuristically classify the type of lead from search result text."""
    text = (title + " " + snippet).lower()

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


def search_serpapi(product_name: str, region: str, description: str, limit: int):
    """
    Search SerpAPI using buyer-intent queries to find leads (potential buyers)
    for the given product in the specified region.
    """
    logger.info("=" * 60)
    logger.info("NEW LEAD SEARCH STARTED")
    logger.info("  Product   : %s", product_name)
    logger.info("  Region    : %s", region)
    logger.info("  Description: %s", description)
    logger.info("  Limit     : %d", limit)
    logger.info("=" * 60)

    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        logger.error("SERPAPI_API_KEY is not set in environment variables!")

    queries = build_buyer_queries(product_name, region, description)
    logger.info("Built %d buyer-intent queries.", len(queries))

    seen_links = set()
    all_leads = []

    for idx, query in enumerate(queries, start=1):
        if len(all_leads) >= limit:
            logger.info("Lead limit (%d) reached — stopping early.", limit)
            break

        logger.info("[Query %d/%d] Firing: %s", idx, len(queries), query)

        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": 10,
            "gl": "us",
            "hl": "en",
        }

        try:
            search = GoogleSearch(params)
            results = search.get_dict()
        except Exception as exc:
            logger.error("SerpAPI call failed for query %d: %s", idx, exc)
            continue

        organic_results = results.get("organic_results", [])
        logger.info("[Query %d/%d] Received %d organic results.", idx, len(queries), len(organic_results))

        added_this_query = 0
        skipped_duplicates = 0

        for result in organic_results:
            if len(all_leads) >= limit:
                logger.info("[Query %d/%d] Lead limit hit mid-results — stopping.", idx, len(queries))
                break

            link = result.get("link", "")
            if not link or link in seen_links:
                skipped_duplicates += 1
                continue  # skip duplicates

            seen_links.add(link)

            title = result.get("title", "")
            snippet = result.get("snippet", "")
            lead_type = classify_lead(title, snippet)

            all_leads.append(
                {
                    "lead_type": lead_type,
                    "title": title,
                    "link": link,
                    "displayed_link": result.get("displayed_link", ""),
                    "source": result.get("source", ""),
                    "snippet": snippet,
                    "matched_query": query,
                }
            )
            added_this_query += 1
            logger.debug("  + Lead added [%s]: %s", lead_type, title)

        logger.info(
            "[Query %d/%d] Added %d leads | Skipped %d duplicates | Total so far: %d",
            idx, len(queries), added_this_query, skipped_duplicates, len(all_leads),
        )

    logger.info("-" * 60)
    logger.info("SEARCH COMPLETE — Total leads found: %d", len(all_leads))
    logger.info("-" * 60)

    return {
        "product_name": product_name,
        "region": region,
        "description": description,
        "total_leads_found": len(all_leads),
        "leads": all_leads,
    }