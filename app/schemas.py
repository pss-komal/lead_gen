from pydantic import BaseModel, EmailStr
from typing import Optional, List


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


# ---------------------------------------------------------------------------
# Lead search schemas  (SerpAPI / Apify / Google Maps Direct)
# ---------------------------------------------------------------------------

class ContextCreate(BaseModel):
    product_name: str
    region:       str
    description:  str
    limit:        int = 10


# ---------------------------------------------------------------------------
# CRM — Save & manage leads
# ---------------------------------------------------------------------------

class LeadSave(BaseModel):
    """Save a single lead from search results into the CRM database."""
    title:        str
    lead_type:    Optional[str] = "Potential Lead"
    phone:        Optional[str] = None
    address:      Optional[str] = None
    category:     Optional[str] = None
    link:         Optional[str] = None
    source:       Optional[str] = None
    matched_query: Optional[str] = None
    product_name: Optional[str] = None
    region:       Optional[str] = None
    score:        Optional[int] = 0
    latitude:     Optional[float] = None
    longitude:    Optional[float] = None


class LeadStatusUpdate(BaseModel):
    """Update the CRM status of a saved lead."""
    status: str      # new | contacted | interested | converted | rejected
    notes:  Optional[str] = None


class LeadNoteUpdate(BaseModel):
    """Add or update manual notes on a saved lead."""
    notes: str


# ---------------------------------------------------------------------------
# AI — Gemini outreach & analysis
# ---------------------------------------------------------------------------

class AIOutreachRequest(BaseModel):
    """Generate AI outreach message for a lead."""
    title:        str
    category:     Optional[str] = None
    lead_type:    Optional[str] = None
    address:      Optional[str] = None
    phone:        Optional[str] = None
    link:         Optional[str] = None
    product_name: str
    sender_name:  str = "Sales Team"


class AIAnalyzeRequest(BaseModel):
    """AI analysis of a single lead."""
    title:        str
    lead_type:    Optional[str] = None
    category:     Optional[str] = None
    address:      Optional[str] = None
    phone:        Optional[str] = None
    link:         Optional[str] = None
    score:        Optional[int] = None
    product_name: str


class AIBatchAnalyzeRequest(BaseModel):
    """AI analysis of a full batch of leads."""
    leads:        List[dict]
    product_name: str
    region:       str


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    """Scrape a website URL for contact information."""
    url: str


class EnrichLeadRequest(BaseModel):
    """Enrich a lead by scraping its website."""
    title:        str
    link:         Optional[str] = None
    phone:        Optional[str] = None
    address:      Optional[str] = None
    lead_type:    Optional[str] = None
    product_name: Optional[str] = None


# ---------------------------------------------------------------------------
# PDF Export
# ---------------------------------------------------------------------------

class PDFExportRequest(BaseModel):
    """Generate a PDF report for a list of leads."""
    leads:        List[dict]
    product_name: str
    region:       str
    description:  str = ""
    score_summary: Optional[dict] = None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

class TelegramMessage(BaseModel):
    """Send a plain text Telegram message."""
    text:    str
    chat_id: Optional[str] = None   # uses TELEGRAM_CHAT_ID from .env if not provided


class TelegramLeadNotify(BaseModel):
    """Send a lead as a Telegram notification."""
    title:    str
    lead_type: Optional[str] = None
    phone:    Optional[str] = None
    address:  Optional[str] = None
    category: Optional[str] = None
    score:    Optional[int] = None
    link:     Optional[str] = None
    source:   Optional[str] = None
    chat_id:  Optional[str] = None


class TelegramHighScoreAlert(BaseModel):
    """Send high-score leads as a Telegram alert."""
    leads:     List[dict]
    threshold: int = 70
    chat_id:   Optional[str] = None


# ---------------------------------------------------------------------------
# Slack / Discord Webhooks
# ---------------------------------------------------------------------------

class WebhookMessage(BaseModel):
    """Send a plain text message to Slack or Discord."""
    text:        str
    webhook_url: Optional[str] = None   # overrides .env value if provided


class WebhookLeadNotify(BaseModel):
    """Send a lead card to Slack or Discord."""
    title:       str
    lead_type:   Optional[str] = None
    phone:       Optional[str] = None
    address:     Optional[str] = None
    category:    Optional[str] = None
    score:       Optional[int] = None
    link:        Optional[str] = None
    source:      Optional[str] = None
    webhook_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Razorpay schemas
# ---------------------------------------------------------------------------

class PaymentOrderCreate(BaseModel):
    amount_inr: float
    currency:   str = "INR"
    receipt:    str = "lead_gen_order"


class PaymentVerify(BaseModel):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str


# ---------------------------------------------------------------------------
# WhatsApp schemas
# ---------------------------------------------------------------------------

class WhatsAppTextMessage(BaseModel):
    to_phone: str
    message:  str


class WhatsAppTemplateMessage(BaseModel):
    to_phone:      str
    template_name: str
    language_code: str = "en_US"


class WhatsAppLeadNotify(BaseModel):
    to_phone:     str
    lead_title:   str
    lead_phone:   Optional[str] = None
    lead_address: Optional[str] = None
    lead_type:    Optional[str] = None
    score:        Optional[int] = None
    link:         Optional[str] = None
    source:       Optional[str] = None


# ---------------------------------------------------------------------------
# Email schemas
# ---------------------------------------------------------------------------

class EmailSend(BaseModel):
    to_email: EmailStr
    subject:  str
    body:     str


class EmailLeadNotify(BaseModel):
    to_email:      EmailStr
    lead_title:    str
    lead_phone:    Optional[str] = None
    lead_address:  Optional[str] = None
    lead_type:     Optional[str] = None
    lead_category: Optional[str] = None
    score:         Optional[int] = None
    link:          Optional[str] = None
    source:        Optional[str] = None