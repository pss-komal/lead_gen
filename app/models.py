from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from .database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


class Lead(Base):
    """
    Saved lead in the CRM database.
    Created when a user saves a lead from any search result.
    """
    __tablename__ = "leads"

    id                  = Column(Integer, primary_key=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Core lead info
    title               = Column(String,  nullable=False)
    lead_type           = Column(String,  default="Potential Lead")
    phone               = Column(String,  nullable=True)
    address             = Column(String,  nullable=True)
    category            = Column(String,  nullable=True)
    link                = Column(String,  nullable=True)
    source              = Column(String,  nullable=True)
    matched_query       = Column(String,  nullable=True)
    product_name        = Column(String,  nullable=True)
    region              = Column(String,  nullable=True)

    # Scoring & GPS
    score               = Column(Integer, default=0)
    latitude            = Column(Float,   nullable=True)
    longitude           = Column(Float,   nullable=True)

    # CRM status tracker: new | contacted | interested | converted | rejected
    status              = Column(String,  default="new")

    # AI & enrichment fields
    ai_outreach_message = Column(Text,    nullable=True)   # from Gemini AI
    scraped_email       = Column(String,  nullable=True)   # from website scraper
    notes               = Column(Text,    nullable=True)   # manual sales notes

    # Timestamps
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)