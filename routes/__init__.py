from .fetch import router as fetch_router
from .send import router as send_router
from .upload import router as upload_router
from .plants import router as plants_router
from .report import router as report_router
from .diagnostics import router as diagnostics_router
from .contacts import router as contacts_router
from .crm import router as crm_router

__all__ = [
    "fetch_router",
    "send_router",
    "upload_router",
    "plants_router",
    "report_router",
    "diagnostics_router",
    "contacts_router",
    "crm_router",
]


