from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from .db import CRMBase


def _utc_now():
    return datetime.now(timezone.utc)


class Customer(CRMBase):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True, autoincrement=True)
    plant_id = Column(String, unique=True, nullable=False, index=True)
    plant_name = Column(String, index=True)
    platform = Column(String, index=True)  # growatt | isolarcloud | suryalog
    customer_name = Column(String, index=True)
    phone_number = Column(String)          # E.164 format: +91XXXXXXXXXX
    opt_in_status = Column(String, default="pending", index=True)  # active | do_not_send | pending
    preferred_lang = Column(String, default="english")            # english | hindi | marathi
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


class MessageQueue(CRMBase):
    __tablename__ = "message_queue"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaign_log.campaign_id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=True, index=True)
    phone_number = Column(String)
    message_text = Column(Text, nullable=False)
    template_used = Column(String)
    month_year = Column(String, index=True)  # e.g. "2025-06"
    status = Column(String, default="PENDING", index=True)  # PENDING | SENT | FAILED | SKIPPED | SIMULATED
    error_reason = Column(String, nullable=True)
    queued_at = Column(DateTime, default=_utc_now)
    sent_at = Column(DateTime, nullable=True)


class CampaignLog(CRMBase):
    __tablename__ = "campaign_log"

    campaign_id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_name = Column(String, nullable=False)
    month_year = Column(String, index=True)
    total_customers = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utc_now)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="DRAFT", index=True)  # DRAFT | RUNNING | COMPLETED | PAUSED
