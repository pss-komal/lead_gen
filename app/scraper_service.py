"""
scraper_service.py  —  Website scraper & email finder (100% FREE).

Uses Python requests + BeautifulSoup to visit a lead's website and extract:
  - Email addresses
  - Phone numbers
  - Social media links (LinkedIn, Twitter, Facebook)
  - Company description

No external paid API needed.

Requires: beautifulsoup4, lxml  (add to requirements.txt)
"""

import re
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("lead_gen.scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Regex patterns
EMAIL_PATTERN   = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN   = re.compile(
    r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{4}"
)


def _get_page_text(url: str, timeout: int = 10):
    """Fetch page HTML safely. Returns (html, error)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text, None
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.SSLError:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            return resp.text, None
        except Exception as exc:
            return None, str(exc)
    except Exception as exc:
        return None, str(exc)


def scrape_website(url: str) -> dict:
    """
    Visit a website URL and extract contact information.

    Parameters
    ----------
    url : str — website URL (e.g. 'https://example.com')

    Returns
    -------
    dict with: emails, phones, social_links, description, pages_checked
    """
    if not url or url.startswith("https://www.google.com/maps"):
        return {
            "success": False,
            "url":     url,
            "error":   "Google Maps URL — no website to scrape.",
        }

    # Normalize URL
    if not url.startswith("http"):
        url = "https://" + url

    logger.info("SCRAPER — visiting: %s", url)

    emails       = set()
    phones       = set()
    social_links = {}
    description  = ""
    pages_checked = []

    # Pages to check for contact info
    base_url    = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    pages_to_try = [url, urljoin(base_url, "/contact"), urljoin(base_url, "/about")]

    for page_url in pages_to_try:
        html, error = _get_page_text(page_url)
        if error or not html:
            continue

        pages_checked.append(page_url)
        soup = BeautifulSoup(html, "lxml")

        # Remove script/style tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        page_text = soup.get_text(separator=" ", strip=True)

        # Extract emails
        found_emails = EMAIL_PATTERN.findall(page_text)
        for email in found_emails:
            if not any(skip in email for skip in ["example", "sentry", "png", "jpg", "svg"]):
                emails.add(email.lower())

        # Extract phones (limited to first 5)
        found_phones = PHONE_PATTERN.findall(page_text)
        for phone in found_phones[:5]:
            cleaned = phone.strip()
            if len(cleaned) >= 7:
                phones.add(cleaned)

        # Extract social links
        for link_tag in soup.find_all("a", href=True):
            href = link_tag["href"]
            if "linkedin.com" in href and "linkedin" not in social_links:
                social_links["linkedin"] = href
            elif "twitter.com" in href or "x.com" in href:
                social_links["twitter"] = href
            elif "facebook.com" in href and "facebook" not in social_links:
                social_links["facebook"] = href
            elif "instagram.com" in href:
                social_links["instagram"] = href

        # Extract description (meta description or first paragraph)
        if not description:
            meta = soup.find("meta", {"name": "description"})
            if meta and meta.get("content"):
                description = meta["content"][:300]
            else:
                first_p = soup.find("p")
                if first_p:
                    description = first_p.get_text(strip=True)[:300]

    result = {
        "success":      True,
        "url":          url,
        "emails":       list(emails),
        "primary_email": list(emails)[0] if emails else None,
        "phones":       list(phones),
        "social_links": social_links,
        "description":  description,
        "pages_checked": pages_checked,
    }

    logger.info(
        "SCRAPER done — emails: %d | phones: %d | socials: %d",
        len(emails), len(phones), len(social_links),
    )
    return result


def enrich_lead(lead: dict) -> dict:
    """
    Convenience function — scrape a lead's website and merge findings into the lead dict.
    Returns enriched lead with scraped_email, social_links, description added.
    """
    link = lead.get("link") or lead.get("website") or ""
    if not link or "google.com/maps" in link:
        lead["enrichment"] = {"skipped": True, "reason": "No website URL available"}
        return lead

    scraped = scrape_website(link)

    lead["scraped_email"]  = scraped.get("primary_email")
    lead["social_links"]   = scraped.get("social_links", {})
    lead["website_description"] = scraped.get("description", "")
    lead["enrichment"]     = {"success": scraped.get("success"), "pages_checked": scraped.get("pages_checked", [])}

    return lead
