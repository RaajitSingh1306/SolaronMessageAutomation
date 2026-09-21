"""
Solaron CRM Package
Customer Engagement, Billing Statements, and WhatsApp Campaign Hub.
"""

from .db import crm_engine, CRMSessionLocal, CRMBase, get_crm_db, init_crm_db
from .models import Customer, MessageQueue, CampaignLog

__all__ = [
    "crm_engine",
    "CRMSessionLocal",
    "CRMBase",
    "get_crm_db",
    "init_crm_db",
    "Customer",
    "MessageQueue",
    "CampaignLog",
]
