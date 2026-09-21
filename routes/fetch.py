import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from config import Config
from helpers import _build_response_data, _config_payload
from services.classifier import classify_plants
from services.excel import save_fetched_data_to_excel
from services.fetcher_orchestrator import SUPPORTED_SOURCES, fetch_from_sources
from services.growatt import GrowattFetcher
from state import (
    FetchRequest,
    YearlyFetchRequest,
    _add_fetch_job,
    get_active_fetch_job,
    get_fetch_job,
    update_fetch_job,
    get_state,
    update_state,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _do_fetch(
    job_id: str,
    target_month: str,
    month_name: str,
    year: str,
    sources: Optional[List[str]],
    save_excel: bool,
    force_refresh: bool,
) -> None:
    def progress_callback(current: int, total: int, msg: str):
        if get_fetch_job(job_id):
            update_fetch_job(
                job_id,
                status="running",
                current=current,
                total=total,
                current_plant=msg,
            )

    def cancel_check():
        job = get_fetch_job(job_id)
        return not job or job.get("status") == "cancelled"

    try:
        update_fetch_job(job_id, status="running", current_plant="Initializing data sources...")
        records, failed, fetch_time = fetch_from_sources(
            target_month=target_month,
            sources=sources,
            force_refresh=force_refresh,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

        if cancel_check():
            logger.info("Fetch job %s was cancelled. Skipping state update.", job_id)
            return

        xlsx_path = None
        if save_excel and records:
            try:
                xlsx_path = save_fetched_data_to_excel(records, month_name, year)
            except Exception as ex:
                logger.warning("Could not export fetched records to excel: %s", ex)

        if records:
            classified = classify_plants(records)
            update_state(
                classified=classified,
                filepath=xlsx_path,
                month_name=month_name,
                year=year,
                sources=sources or SUPPORTED_SOURCES,
                response_data=None,
            )

            data, counts = _build_response_data()

            update_fetch_job(
                job_id,
                status="done",
                data=data,
                counts=counts,
                config=_config_payload(),
                from_cache=False,
                fetch_stats={
                    "total_plants_fetched": len(records),
                    "fetch_time_seconds": fetch_time,
                    "failed": failed,
                    "sources": sources or SUPPORTED_SOURCES,
                },
            )
        else:
            err_msg = "Failed to fetch plants from requested sources."
            if failed:
                err_msg += f" Errors: {failed}"
            update_fetch_job(job_id, status="error", error=err_msg)

    except Exception as exc:
        logger.exception("Background fetch job %s failed: %s", job_id, exc)
        if get_fetch_job(job_id):
            update_fetch_job(job_id, status="error", error=str(exc))


@router.post("/api/fetch")
def fetch_solar_data(body: FetchRequest, background_tasks: BackgroundTasks):
    target_month = body.month
    if not target_month:
        target_month = datetime.now().strftime("%Y-%m")

    sources = body.sources
    if not sources:
        sources = SUPPORTED_SOURCES
    else:
        sources = [s.lower().strip() for s in sources if s.lower().strip() in SUPPORTED_SOURCES]
        if not sources:
            sources = SUPPORTED_SOURCES

    save_excel = body.save_excel

    try:
        dt = datetime.strptime(target_month, "%Y-%m")
        month_name = dt.strftime("%B")
        year = dt.strftime("%Y")
    except ValueError:
        return JSONResponse(
            {"success": False, "message": "Invalid month format. Use YYYY-MM."},
            status_code=400,
        )

    active_job = get_active_fetch_job()
    if active_job:
        act_id, act_data = active_job
        act_sources = set(act_data.get("sources", []))
        req_sources = set(sources)
        # If user explicitly requested different sources or month, cancel previous job and start new one
        if act_sources == req_sources and act_data.get("target_month") == target_month:
            logger.info("Fetch job %s is already running for identical request. Returning active job.", act_id)
            return {
                "success": True,
                "job_id": act_id,
                "message": f"Fetch already in progress in background.",
            }
        else:
            logger.info("Cancelling previous fetch job %s (sources: %s) because new fetch has sources: %s", act_id, act_sources, req_sources)
            update_fetch_job(act_id, status="cancelled", error="Cancelled by new fetch request.")

    try:
        job_id = str(uuid.uuid4())
        _add_fetch_job(
            job_id,
            {
                "status": "queued",
                "current": 0,
                "total": len(sources),
                "current_plant": "Starting fetch...",
                "sources": sources,
                "target_month": target_month,
            },
        )

        background_tasks.add_task(
            _do_fetch,
            job_id,
            target_month,
            month_name,
            year,
            sources,
            save_excel,
            body.force_refresh,
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Fetch started in background for sources: {', '.join(sources)}",
        }

    except Exception as exc:
        logger.exception("Error starting multi-source fetch.")
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@router.post("/api/fetch/cancel")
def cancel_active_fetch():
    active_job = get_active_fetch_job()
    if active_job:
        act_id, act_data = active_job
        update_fetch_job(act_id, status="cancelled", error="Cancelled by user.")
        logger.info("Active fetch job %s cancelled via API.", act_id)
        return {"success": True, "message": "Active fetch job cancelled."}
    return {"success": True, "message": "No active fetch job running."}


def _do_fetch_yearly(
    job_id: str,
    target_year: int,
    sources: Optional[List[str]],
) -> None:
    from services.fetcher_orchestrator import fetch_yearly_from_sources
    from services.history import enrich_records_with_history

    def progress_callback(current: int, total: int, msg: str):
        if get_fetch_job(job_id):
            update_fetch_job(
                job_id,
                status="running",
                current=current,
                total=total,
                current_plant=msg,
            )

    try:
        update_fetch_job(job_id, status="running", current_plant=f"Starting yearly data fetch for {target_year}...")
        results, failed, fetch_time = fetch_yearly_from_sources(
            target_year=target_year,
            sources=sources,
            progress_callback=progress_callback,
        )

        # Enrich current state records with the newly fetched history
        state = get_state()
        if state.classified:
            all_records = []
            for plant_list in state.classified.values():
                all_records.extend(plant_list)
            enrich_records_with_history(all_records, target_year=target_year)
            update_state(response_data=None)

        data, counts = _build_response_data()

        update_fetch_job(
            job_id,
            status="done",
            data=data,
            counts=counts,
            config=_config_payload(),
            fetch_stats={
                "target_year": target_year,
                "total_histories_fetched": len(results),
                "fetch_time_seconds": fetch_time,
                "failed": failed,
                "sources": sources or SUPPORTED_SOURCES,
            },
        )
    except Exception as exc:
        logger.exception("Yearly background fetch job %s failed: %s", job_id, exc)
        if get_fetch_job(job_id):
            update_fetch_job(job_id, status="error", error=str(exc))


@router.post("/api/fetch-yearly")
def fetch_yearly_solar_data(body: YearlyFetchRequest, background_tasks: BackgroundTasks):
    target_year = body.year
    if not target_year:
        state = get_state()
        if state.year and state.year.isdigit():
            target_year = int(state.year)
        else:
            target_year = datetime.now().year

    sources = body.sources
    if not sources:
        sources = SUPPORTED_SOURCES
    else:
        sources = [s.lower().strip() for s in sources if s.lower().strip() in SUPPORTED_SOURCES]
        if not sources:
            sources = SUPPORTED_SOURCES

    active_job = get_active_fetch_job()
    if active_job:
        act_id, act_data = active_job
        return {
            "success": True,
            "job_id": act_id,
            "message": "A fetch operation is already in progress.",
        }

    try:
        job_id = str(uuid.uuid4())
        _add_fetch_job(
            job_id,
            {
                "status": "queued",
                "current": 0,
                "total": len(sources),
                "current_plant": f"Starting yearly fetch for {target_year}...",
                "sources": sources,
                "fetch_type": "yearly",
            },
        )

        background_tasks.add_task(
            _do_fetch_yearly,
            job_id,
            target_year,
            sources,
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Yearly history fetch started for year {target_year} across sources: {', '.join(sources)}",
        }
    except Exception as exc:
        logger.exception("Error initiating yearly fetch: %s", exc)
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@router.get("/api/fetch-status/{job_id}")
def get_fetch_status(job_id: str):
    job = get_fetch_job(job_id)
    if not job:
        return {
            "success": True,
            "status": "error",
            "error": "Job expired or backend restarted. Please try again.",
        }
    return {"success": True, "job_id": job_id, **job}
