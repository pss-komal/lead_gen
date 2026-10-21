import logging
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import io
import csv

from .database import Base, engine, get_db
from .models   import User, Lead as LeadModel
from .schemas  import (
    UserCreate, Token, ContextCreate,
    LeadSave, LeadStatusUpdate, LeadNoteUpdate,
    AIOutreachRequest, AIAnalyzeRequest, AIBatchAnalyzeRequest,
    ScrapeRequest, EnrichLeadRequest,
    PDFExportRequest,
    TelegramMessage, TelegramLeadNotify, TelegramHighScoreAlert,
    WebhookMessage, WebhookLeadNotify,
    PaymentOrderCreate, PaymentVerify,
    WhatsAppTextMessage, WhatsAppTemplateMessage, WhatsAppLeadNotify,
    EmailSend, EmailLeadNotify,
)
from .auth import hash_password, verify_password, create_access_token, get_current_user

# --- Services ---
from .serp_service        import search_serpapi
from .apify_service       import search_apify
from .google_maps_service import search_google_maps
from .gemini_service      import generate_outreach_message, analyze_lead, summarize_leads_batch
from .telegram_service    import send_message as tg_send, send_lead_notification, send_high_score_alert, send_search_summary
from .scraper_service     import scrape_website, enrich_lead
from .pdf_service         import generate_leads_pdf
from .webhook_service     import (
    send_slack_message, send_slack_lead, send_slack_summary,
    send_discord_message, send_discord_lead, notify_all_channels,
)
from .razorpay_service    import create_order, verify_payment, get_payment_details
from .whatsapp_service    import send_text_message, send_template_message, send_lead_to_whatsapp
from .email_service       import send_email, send_lead_email

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("lead_gen.main")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Lead Gen CRM API",
    description=(
        "Full-stack Lead Generation CRM with direct integrations:\n"
        "Google Maps API • Gemini AI • Telegram Bot • Razorpay • "
        "WhatsApp • Gmail SMTP • Slack • Discord • PDF Export • Website Scraper"
    ),
    version="3.0.0",
)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    logger.info("=" * 60)
    logger.info("Lead Gen CRM API v3.0  —  startup complete")
    logger.info("Docs: http://127.0.0.1:8000/docs")
    logger.info("=" * 60)


@app.on_event("shutdown")
def on_shutdown():
    logger.info("Lead Gen API  —  shutting down.")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root(request: Request):
    return {"message": "Lead Gen CRM API v3.0 is running", "docs": "/docs"}


# ===========================================================================
# AUTH
# ===========================================================================

@app.post("/register", response_model=Token, tags=["Auth"])
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = User(email=user.email, hashed_password=hash_password(user.password))
    db.add(new_user); db.commit(); db.refresh(new_user)
    return {"access_token": create_access_token({"sub": new_user.email}), "token_type": "bearer"}


@app.post("/login", response_model=Token, tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer"}


# ===========================================================================
# LEAD SEARCH ENGINES
# ===========================================================================

@app.post("/context/create", tags=["Lead Search — SerpAPI"])
def create_context(payload: ContextCreate, current_user: User = Depends(get_current_user)):
    """Search leads via SerpAPI Google Maps (middleman)."""
    return search_serpapi(payload.product_name, payload.region, payload.description, payload.limit)


@app.post("/apify/search", tags=["Lead Search — Apify"])
def apify_search(payload: ContextCreate, current_user: User = Depends(get_current_user)):
    """Search leads via Apify Google Maps Scraper (middleman)."""
    return search_apify(payload.product_name, payload.region, payload.description, payload.limit)


@app.post("/google/search", tags=["Lead Search — Google Direct"])
def google_search(payload: ContextCreate, current_user: User = Depends(get_current_user)):
    """Search leads directly via Google Places API (no middleman). Requires GOOGLE_MAPS_API_KEY."""
    return search_google_maps(payload.product_name, payload.region, payload.description, payload.limit)


# ===========================================================================
# CRM — LEAD DATABASE (Save, Track, Manage)
# ===========================================================================

@app.post("/leads/save", tags=["CRM — Lead Database"])
def save_lead(payload: LeadSave, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Save a lead from search results into your personal CRM database."""
    lead = LeadModel(
        user_id      = current_user.id,
        title        = payload.title,
        lead_type    = payload.lead_type,
        phone        = payload.phone,
        address      = payload.address,
        category     = payload.category,
        link         = payload.link,
        source       = payload.source,
        matched_query = payload.matched_query,
        product_name = payload.product_name,
        region       = payload.region,
        score        = payload.score or 0,
        latitude     = payload.latitude,
        longitude    = payload.longitude,
    )
    db.add(lead); db.commit(); db.refresh(lead)
    logger.info("Lead saved: %s (id=%d) by user %s", lead.title, lead.id, current_user.email)
    return {"success": True, "lead_id": lead.id, "title": lead.title, "status": lead.status}


@app.get("/leads", tags=["CRM — Lead Database"])
def get_leads(
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all saved leads for current user. Filter by status: new|contacted|interested|converted|rejected"""
    query = db.query(LeadModel).filter(LeadModel.user_id == current_user.id)
    if status:
        query = query.filter(LeadModel.status == status)
    leads = query.order_by(LeadModel.score.desc()).all()

    return {
        "total": len(leads),
        "leads": [
            {
                "id": l.id, "title": l.title, "lead_type": l.lead_type,
                "phone": l.phone, "address": l.address, "category": l.category,
                "link": l.link, "score": l.score, "status": l.status,
                "product_name": l.product_name, "region": l.region,
                "ai_outreach_message": l.ai_outreach_message,
                "scraped_email": l.scraped_email, "notes": l.notes,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ],
    }


@app.get("/leads/stats", tags=["CRM — Lead Database"])
def lead_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get CRM statistics — status breakdown, conversion rate, avg score."""
    leads = db.query(LeadModel).filter(LeadModel.user_id == current_user.id).all()
    if not leads:
        return {"total": 0, "message": "No leads saved yet."}

    status_counts = {}
    for lead in leads:
        status_counts[lead.status] = status_counts.get(lead.status, 0) + 1

    scores        = [l.score for l in leads if l.score]
    converted     = status_counts.get("converted", 0)

    return {
        "total_leads":       len(leads),
        "status_breakdown":  status_counts,
        "conversion_rate":   f"{(converted / len(leads) * 100):.1f}%" if leads else "0%",
        "avg_score":         round(sum(scores) / len(scores), 1) if scores else 0,
        "top_score":         max(scores) if scores else 0,
    }


@app.patch("/leads/{lead_id}/status", tags=["CRM — Lead Database"])
def update_lead_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update CRM status of a saved lead (new→contacted→interested→converted/rejected)."""
    valid = {"new", "contacted", "interested", "converted", "rejected"}
    if payload.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid}")

    lead = db.query(LeadModel).filter(LeadModel.id == lead_id, LeadModel.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    lead.status     = payload.status
    lead.updated_at = datetime.utcnow()
    if payload.notes:
        lead.notes = payload.notes
    db.commit()
    return {"success": True, "lead_id": lead_id, "new_status": payload.status}


@app.delete("/leads/{lead_id}", tags=["CRM — Lead Database"])
def delete_lead(
    lead_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a saved lead from CRM."""
    lead = db.query(LeadModel).filter(LeadModel.id == lead_id, LeadModel.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    db.delete(lead); db.commit()
    return {"success": True, "deleted_lead_id": lead_id}


@app.patch("/leads/{lead_id}/note", tags=["CRM — Lead Database"])
def update_lead_note(
    lead_id: int,
    payload: LeadNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add or update sales notes on a saved lead."""
    lead = db.query(LeadModel).filter(LeadModel.id == lead_id, LeadModel.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    lead.notes = payload.notes
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "lead_id": lead_id, "notes": lead.notes}


@app.get("/leads/export/csv", tags=["CRM — Lead Database"])
def export_crm_leads_csv(
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Export all saved CRM leads to a downloadable CSV file.
    Can be opened directly in Microsoft Excel or imported into Google Sheets.
    """
    query = db.query(LeadModel).filter(LeadModel.id == LeadModel.id, LeadModel.user_id == current_user.id)
    if status:
        query = query.filter(LeadModel.status == status)
    leads = query.order_by(LeadModel.score.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Title", "Lead Type", "Score", "Status",
        "Phone", "Scraped Email", "Address", "Category",
        "Website", "Product", "Region", "Notes", "AI Outreach Message", "Created At"
    ])
    for l in leads:
        writer.writerow([
            l.id, l.title, l.lead_type, l.score, l.status,
            l.phone, l.scraped_email, l.address, l.category,
            l.link, l.product_name, l.region, l.notes, l.ai_outreach_message,
            l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else ""
        ])

    output.seek(0)
    filename = f"crm_leads_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ===========================================================================
# AI — GOOGLE GEMINI (Free: 1M tokens/month)
# ===========================================================================

@app.post("/ai/generate-message", tags=["AI — Gemini (Free)"])
def ai_generate_message(payload: AIOutreachRequest, current_user: User = Depends(get_current_user)):
    """
    Generate a personalized WhatsApp/email outreach message for a lead using Gemini AI.
    Requires GEMINI_API_KEY in .env (free at aistudio.google.com)
    """
    lead_dict = {
        "title": payload.title, "category": payload.category,
        "lead_type": payload.lead_type, "address": payload.address,
        "phone": payload.phone, "link": payload.link,
    }
    return generate_outreach_message(lead_dict, payload.product_name, payload.sender_name)


@app.post("/ai/analyze-lead", tags=["AI — Gemini (Free)"])
def ai_analyze_lead(payload: AIAnalyzeRequest, current_user: User = Depends(get_current_user)):
    """
    Use Gemini AI to intelligently analyze a lead's quality and suggest next action.
    Returns: ai_fit_score, ai_reasoning, ai_recommended_action
    """
    lead_dict = {
        "title": payload.title, "lead_type": payload.lead_type,
        "category": payload.category, "address": payload.address,
        "phone": payload.phone, "link": payload.link, "score": payload.score,
    }
    return analyze_lead(lead_dict, payload.product_name)


@app.post("/ai/analyze-batch", tags=["AI — Gemini (Free)"])
def ai_analyze_batch(payload: AIBatchAnalyzeRequest, current_user: User = Depends(get_current_user)):
    """
    Use Gemini AI to analyze the full batch of leads and give strategic insights.
    Returns: summary, top_leads, strategy, red_flags
    """
    return summarize_leads_batch(payload.leads, payload.product_name, payload.region)


@app.post("/ai/save-message/{lead_id}", tags=["AI — Gemini (Free)"])
def ai_save_message_to_lead(
    lead_id: int,
    payload: AIOutreachRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate AI message for a lead AND save it directly to that lead's CRM record."""
    lead = db.query(LeadModel).filter(LeadModel.id == lead_id, LeadModel.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    lead_dict = {"title": lead.title, "category": lead.category, "lead_type": lead.lead_type, "address": lead.address}
    result    = generate_outreach_message(lead_dict, payload.product_name, payload.sender_name)

    lead.ai_outreach_message = result.get("ai_message", "")
    lead.updated_at          = datetime.utcnow()
    db.commit()

    return {"success": True, "lead_id": lead_id, "ai_message": lead.ai_outreach_message}


# ===========================================================================
# SCRAPER — WEBSITE EMAIL FINDER (Free)
# ===========================================================================

@app.post("/scrape/website", tags=["Scraper — Email Finder (Free)"])
def scrape_website_endpoint(payload: ScrapeRequest, current_user: User = Depends(get_current_user)):
    """
    Scrape any website URL to extract: emails, phones, social links, description.
    Completely free — uses BeautifulSoup internally.
    """
    return scrape_website(payload.url)


@app.post("/scrape/enrich-lead", tags=["Scraper — Email Finder (Free)"])
def enrich_lead_endpoint(payload: EnrichLeadRequest, current_user: User = Depends(get_current_user)):
    """
    Enrich a lead by auto-scraping its website.
    Adds: scraped_email, social_links, website_description to the lead.
    """
    lead_dict = {"title": payload.title, "link": payload.link, "phone": payload.phone, "address": payload.address}
    return enrich_lead(lead_dict)


@app.post("/scrape/enrich-save/{lead_id}", tags=["Scraper — Email Finder (Free)"])
def enrich_and_save(
    lead_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scrape the website of a saved CRM lead and update its record with the email found."""
    lead = db.query(LeadModel).filter(LeadModel.id == lead_id, LeadModel.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if not lead.link:
        raise HTTPException(status_code=400, detail="This lead has no website URL to scrape.")

    scraped = scrape_website(lead.link)
    if scraped.get("primary_email"):
        lead.scraped_email = scraped["primary_email"]
        lead.updated_at    = datetime.utcnow()
        db.commit()

    return {"success": True, "lead_id": lead_id, "scraped_email": lead.scraped_email, "all_emails": scraped.get("emails", [])}


# ===========================================================================
# PDF EXPORT (Free)
# ===========================================================================

@app.post("/export/pdf", tags=["Export — PDF Report (Free)"])
def export_pdf(payload: PDFExportRequest, current_user: User = Depends(get_current_user)):
    """
    Generate and download a professional PDF report for a list of leads.
    Uses reportlab — completely free.
    """
    pdf_bytes = generate_leads_pdf(
        leads         = payload.leads,
        product_name  = payload.product_name,
        region        = payload.region,
        description   = payload.description,
        score_summary = payload.score_summary,
    )
    filename = f"leads_{payload.product_name.replace(' ', '_')}_{payload.region}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/export/csv", tags=["Export — PDF & CSV (Free)"])
def export_csv(payload: PDFExportRequest, current_user: User = Depends(get_current_user)):
    """
    Generate and download a CSV file of search results leads.
    Ready to import into Google Sheets or open in Microsoft Excel.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "Lead Type", "Score", "Phone", "Address",
        "Category", "Website", "Product", "Region", "Summary"
    ])
    for l in payload.leads:
        writer.writerow([
            l.get("title", ""),
            l.get("lead_type", ""),
            l.get("score", 0),
            l.get("phone", ""),
            l.get("address", ""),
            l.get("category", ""),
            l.get("link", ""),
            payload.product_name,
            payload.region,
            l.get("snippet", "") or l.get("description", ""),
        ])

    output.seek(0)
    filename = f"leads_{payload.product_name.replace(' ', '_')}_{payload.region}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ===========================================================================
# TELEGRAM BOT (100% Free)
# ===========================================================================

@app.post("/telegram/send", tags=["Telegram Bot — Free"])
def telegram_send(payload: TelegramMessage, current_user: User = Depends(get_current_user)):
    """Send a plain text message to Telegram. Requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID."""
    result = tg_send(payload.text, payload.chat_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/telegram/notify-lead", tags=["Telegram Bot — Free"])
def telegram_notify_lead(payload: TelegramLeadNotify, current_user: User = Depends(get_current_user)):
    """Send a formatted lead card to Telegram instantly."""
    lead_dict = {
        "title": payload.title, "lead_type": payload.lead_type,
        "phone": payload.phone, "address": payload.address,
        "category": payload.category, "score": payload.score,
        "link": payload.link, "source": payload.source,
    }
    result = send_lead_notification(lead_dict, payload.chat_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/telegram/high-score-alert", tags=["Telegram Bot — Free"])
def telegram_high_score_alert(payload: TelegramHighScoreAlert, current_user: User = Depends(get_current_user)):
    """
    Filter leads above score threshold and send a batch summary alert to Telegram.
    Perfect to call right after a lead search.
    """
    result = send_high_score_alert(payload.leads, payload.threshold, payload.chat_id)
    return result


# ===========================================================================
# SLACK WEBHOOKS (Free)
# ===========================================================================

@app.post("/slack/send", tags=["Slack Webhook — Free"])
def slack_send(payload: WebhookMessage, current_user: User = Depends(get_current_user)):
    """Send a plain text message to Slack channel via Incoming Webhook."""
    result = send_slack_message(payload.text, payload.webhook_url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/slack/notify-lead", tags=["Slack Webhook — Free"])
def slack_notify_lead(payload: WebhookLeadNotify, current_user: User = Depends(get_current_user)):
    """Send a rich Slack Block Kit lead card to your Slack channel."""
    lead_dict = {
        "title": payload.title, "lead_type": payload.lead_type, "phone": payload.phone,
        "address": payload.address, "category": payload.category, "score": payload.score,
        "link": payload.link, "source": payload.source,
    }
    result = send_slack_lead(lead_dict, payload.webhook_url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ===========================================================================
# DISCORD WEBHOOKS (Free)
# ===========================================================================

@app.post("/discord/send", tags=["Discord Webhook — Free"])
def discord_send(payload: WebhookMessage, current_user: User = Depends(get_current_user)):
    """Send a plain text message to Discord via Webhook."""
    result = send_discord_message(payload.text, payload.webhook_url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/discord/notify-lead", tags=["Discord Webhook — Free"])
def discord_notify_lead(payload: WebhookLeadNotify, current_user: User = Depends(get_current_user)):
    """Send a rich Discord embed lead card to your Discord channel."""
    lead_dict = {
        "title": payload.title, "lead_type": payload.lead_type, "phone": payload.phone,
        "address": payload.address, "category": payload.category, "score": payload.score,
        "link": payload.link, "source": payload.source,
    }
    result = send_discord_lead(lead_dict, payload.webhook_url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/notify/all-channels", tags=["Notify All Channels"])
def notify_all(payload: WebhookLeadNotify, current_user: User = Depends(get_current_user)):
    """Send a lead notification to BOTH Slack and Discord simultaneously."""
    lead_dict = {
        "title": payload.title, "lead_type": payload.lead_type, "phone": payload.phone,
        "address": payload.address, "category": payload.category, "score": payload.score,
        "link": payload.link, "source": payload.source,
    }
    return notify_all_channels(lead_dict)


# ===========================================================================
# PAYMENTS — Razorpay Direct
# ===========================================================================

@app.post("/payments/create-order", tags=["Payments — Razorpay Direct"])
def payment_create_order(payload: PaymentOrderCreate, current_user: User = Depends(get_current_user)):
    """Create a Razorpay payment order. Requires RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET."""
    result = create_order(payload.amount_inr, payload.currency, payload.receipt)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/payments/verify", tags=["Payments — Razorpay Direct"])
def payment_verify(payload: PaymentVerify, current_user: User = Depends(get_current_user)):
    """Verify Razorpay payment signature after user checkout."""
    result = verify_payment(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.get("/payments/{payment_id}", tags=["Payments — Razorpay Direct"])
def payment_details(payment_id: str, current_user: User = Depends(get_current_user)):
    """Fetch Razorpay payment details by payment_id."""
    result = get_payment_details(payment_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


# ===========================================================================
# WHATSAPP — Meta Direct
# ===========================================================================

@app.post("/whatsapp/send", tags=["WhatsApp — Meta Direct"])
def whatsapp_send(payload: WhatsAppTextMessage, current_user: User = Depends(get_current_user)):
    """Send WhatsApp text message. Requires WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_ACCESS_TOKEN."""
    result = send_text_message(payload.to_phone, payload.message)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/whatsapp/send-template", tags=["WhatsApp — Meta Direct"])
def whatsapp_send_template(payload: WhatsAppTemplateMessage, current_user: User = Depends(get_current_user)):
    """Send a pre-approved WhatsApp template message (required for first-time contact)."""
    result = send_template_message(payload.to_phone, payload.template_name, payload.language_code)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/whatsapp/notify-lead", tags=["WhatsApp — Meta Direct"])
def whatsapp_notify_lead(payload: WhatsAppLeadNotify, current_user: User = Depends(get_current_user)):
    """Send formatted lead card as WhatsApp message to a sales rep."""
    lead_dict = {"title": payload.lead_title, "phone": payload.lead_phone, "address": payload.lead_address,
                 "lead_type": payload.lead_type, "score": payload.score, "link": payload.link, "source": payload.source}
    result = send_lead_to_whatsapp(payload.to_phone, lead_dict)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ===========================================================================
# EMAIL — Gmail SMTP Direct
# ===========================================================================

@app.post("/email/send", tags=["Email — Gmail Direct"])
def email_send(payload: EmailSend, current_user: User = Depends(get_current_user)):
    """Send plain text email via Gmail SMTP. Requires GMAIL_SENDER_EMAIL + GMAIL_APP_PASSWORD."""
    result = send_email(payload.to_email, payload.subject, payload.body)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/email/notify-lead", tags=["Email — Gmail Direct"])
def email_notify_lead(payload: EmailLeadNotify, current_user: User = Depends(get_current_user)):
    """Send a professional HTML lead card email to a sales rep."""
    lead_dict = {"title": payload.lead_title, "phone": payload.lead_phone, "address": payload.lead_address,
                 "lead_type": payload.lead_type, "category": payload.lead_category,
                 "score": payload.score, "link": payload.link, "source": payload.source}
    result = send_lead_email(payload.to_email, lead_dict)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result
