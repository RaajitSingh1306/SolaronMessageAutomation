import logging
import os
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse

from config import Config
from helpers import _config_payload
from services.report import export_report_to_csv, format_report_rows, get_report_summary
from state import get_state

logger = logging.getLogger(__name__)
router = APIRouter()


from services.scheduler import hydrate_state_from_cache


def _get_all_state_records():
    state = get_state()
    if not state.classified:
        hydrate_state_from_cache()
        state = get_state()
    records = []
    for plant_list in state.classified.values():
        records.extend(plant_list)
    return records, state


@router.get("/api/report")
def get_report(
    view: str = Query("monthly", description="Report view mode: daily, weekly, monthly, or yearly"),
    source: Optional[str] = Query(None, description="Optional filter by source (growatt, isolarcloud, suryalog)"),
    sort_by: str = Query("name", description="Sort by: name, capacity, energy, saving, yield, deviation"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    year: Optional[str] = Query(None, description="Target year for yearly reports"),
    date: Optional[str] = Query(None, description="Target date for daily reports (e.g. YYYY-MM-DD or yesterday)"),
):
    records, state = _get_all_state_records()
    if not records:
        return JSONResponse(
            {
                "success": False,
                "message": "No data loaded yet. Please fetch data or upload a file first.",
                "rows": [],
                "summary": {},
            },
            status_code=200,
        )

    if source:
        src_clean = source.lower().strip()
        records = [r for r in records if getattr(r, "source", "").lower() == src_clean]

    target_year = year or state.year
    rows = format_report_rows(
        records,
        view_mode=view,
        price_per_unit=Config.PRICE_PER_UNIT,
        sort_by=sort_by,
        sort_order=sort_order,
        year_label=target_year,
        target_date=date,
    )
    summary = get_report_summary(
        records,
        month_name=state.month_name,
        year=target_year,
        view_mode=view,
        target_date=date,
    )

    return {
        "success": True,
        "view": view,
        "date": date,
        "source": source or "all",
        "sort_by": sort_by,
        "sort_order": sort_order,
        "month_name": state.month_name,
        "year": target_year,
        "total_rows": len(rows),
        "rows": rows,
        "summary": summary,
        "config": _config_payload(),
    }


@router.get("/api/report/summary")
def get_summary():
    records, state = _get_all_state_records()
    if not records:
        return {
            "success": False,
            "message": "No data loaded.",
            "summary": {
                "total_plants": 0,
                "total_energy_month_kwh": 0,
                "total_energy_today_kwh": 0,
                "total_savings_month_inr": 0,
                "by_status": {"Active": 0, "Offline": 0, "Not Commissioned": 0},
                "by_source": {},
            },
        }

    summary = get_report_summary(records, month_name=state.month_name, year=state.year)
    return {"success": True, "summary": summary}


@router.get("/api/report/csv")
def download_report_csv(
    view: str = Query("monthly", description="daily, weekly, monthly, or yearly"),
    source: Optional[str] = Query(None, description="Optional source filter"),
    sort_by: str = Query("name", description="Sort by: name, capacity, energy, saving"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    year: Optional[str] = Query(None, description="Target year for report"),
):
    records, state = _get_all_state_records()
    if not records:
        return JSONResponse(
            {"success": False, "error": "No data loaded to export."},
            status_code=400,
        )

    if source:
        src_clean = source.lower().strip()
        records = [r for r in records if getattr(r, "source", "").lower() == src_clean]

    target_year = year or state.year
    csv_path = export_report_to_csv(
        records=records,
        view_mode=view,
        month_name=state.month_name,
        year=target_year,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    filename = os.path.basename(csv_path)
    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename=filename,
    )

