import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple
import threading
from dataclasses import dataclass, field

from pydantic import BaseModel

from config import Config
from services.contacts import get_phone_number, save_cache
from services.messaging import generate_message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory session state
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()

@dataclass
class AppState:
    classified: dict = field(default_factory=dict)
    filepath: Optional[str] = None
    month_name: str = ""
    year: str = ""
    response_data: Optional[Tuple[Dict, Dict]] = None
    report_view: str = "monthly"
    sources: List[str] = field(default_factory=list)

    @property
    def month(self) -> str:
        """Returns month formatted as YYYY-MM based on year and month_name."""
        if self.year and self.month_name:
            try:
                from datetime import datetime
                m_num = datetime.strptime(self.month_name[:3], "%b").month
                return f"{self.year}-{m_num:02d}"
            except Exception:
                pass
        return ""

_state = AppState()

def get_state() -> AppState:
    with _state_lock:
        return AppState(
            classified=_state.classified,
            filepath=_state.filepath,
            month_name=_state.month_name,
            year=_state.year,
            response_data=_state.response_data,
            report_view=_state.report_view,
            sources=_state.sources,
        )

def update_state(**kwargs) -> None:
    with _state_lock:
        for k, v in kwargs.items():
            if hasattr(_state, k):
                setattr(_state, k, v)

# Background send jobs
_send_jobs: dict = {}
_MAX_SEND_JOBS = 200

def _add_job(job_id: str, job_data: dict) -> None:
    with _state_lock:
        if len(_send_jobs) >= _MAX_SEND_JOBS:
            oldest = next(iter(_send_jobs))
            del _send_jobs[oldest]
        _send_jobs[job_id] = job_data

def get_send_job(job_id: str) -> Optional[dict]:
    with _state_lock:
        return _send_jobs.get(job_id)

def update_send_job(job_id: str, **kwargs) -> None:
    with _state_lock:
        if job_id in _send_jobs:
            _send_jobs[job_id].update(kwargs)

# Background fetch jobs
_fetch_jobs: dict = {}
_MAX_FETCH_JOBS = 50

def _add_fetch_job(job_id: str, job_data: dict) -> None:
    with _state_lock:
        if len(_fetch_jobs) >= _MAX_FETCH_JOBS:
            oldest = next(iter(_fetch_jobs))
            del _fetch_jobs[oldest]
        _fetch_jobs[job_id] = job_data

def get_fetch_job(job_id: str) -> Optional[dict]:
    with _state_lock:
        return _fetch_jobs.get(job_id)

def update_fetch_job(job_id: str, **kwargs) -> None:
    with _state_lock:
        if job_id in _fetch_jobs:
            _fetch_jobs[job_id].update(kwargs)

def get_active_fetch_job() -> Optional[Tuple[str, dict]]:
    with _state_lock:
        for j_id, j_data in reversed(list(_fetch_jobs.items())):
            if j_data.get("status") in ("running", "queued"):
                return j_id, j_data
        return None


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class FetchRequest(BaseModel):
    month: Optional[str] = None
    sources: Optional[List[str]] = None
    save_excel: bool = True
    force_refresh: bool = False

class YearlyFetchRequest(BaseModel):
    year: Optional[int] = None
    sources: Optional[List[str]] = None

class SendRequest(BaseModel):
    plants: List[str] = []
    view: Optional[str] = "monthly"
    gap_seconds: Optional[int] = 3
    manual_mode: Optional[bool] = True

class TestSendRequest(BaseModel):
    phone: Optional[str] = None
    message: Optional[str] = None



# Helpers moved to helpers.py
