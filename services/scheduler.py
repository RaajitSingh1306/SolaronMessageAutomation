"""
services/scheduler.py

Automated background scheduler and state hydration engine for Solaron Dashboard.
- Automatically hydrates in-memory AppState from fresh disk cache on launch (zero wait).
- Automatically triggers background fetch if cache is missing or expired.
- Scheduled daily generation syncing and 1st-of-the-month report generation.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config import Config
from services.classifier import classify_plants
from services.excel import PlantRecord, save_fetched_data_to_excel
from services.fetcher_orchestrator import SUPPORTED_SOURCES, fetch_from_sources
from services.growatt import get_cached_data as get_growatt_cache
from services.isolarcloud import get_cached_data as get_isolar_cache
from services.suryalog import get_cached_data as get_suryalog_cache
from state import get_state, update_state

logger = logging.getLogger(__name__)


def hydrate_state_from_cache(target_month: Optional[str] = None) -> bool:
    """
    Attempt to load cached plant records for target_month into AppState.
    If target_month is None, checks current month, then falls back to previous month.

    Returns:
        True if records were loaded and classified into AppState, False otherwise.
    """
    state = get_state()
    if state.classified and sum(len(v) for v in state.classified.values()) > 0:
        logger.debug("[Auto-Hydrate] State already has classified data, skipping cache hydration.")
        return True

    now = datetime.now()
    candidate_months: List[str] = []

    if target_month:
        candidate_months.append(target_month)
    else:
        current_m = now.strftime("%Y-%m")
        # Previous month
        first_of_current = now.replace(day=1)
        prev_m = (first_of_current - timedelta(days=1)).strftime("%Y-%m")
        candidate_months = [current_m, prev_m]

    for month_str in candidate_months:
        all_records: List[PlantRecord] = []
        sources_found: List[str] = []

        # 1. Growatt
        try:
            gw = get_growatt_cache(month_str)
            if gw and gw[0]:
                all_records.extend(gw[0])
                sources_found.append("growatt")
        except Exception as e:
            logger.debug("[Auto-Hydrate] Growatt cache check note: %s", e)

        # 2. iSolarCloud
        try:
            isc = get_isolar_cache(month_str)
            if isc and isc[0]:
                all_records.extend(isc[0])
                sources_found.append("isolarcloud")
        except Exception as e:
            logger.debug("[Auto-Hydrate] iSolarCloud cache check note: %s", e)

        # 3. SuryaLog
        try:
            sl = get_suryalog_cache(month_str)
            if sl and sl[0]:
                all_records.extend(sl[0])
                sources_found.append("suryalog")
        except Exception as e:
            logger.debug("[Auto-Hydrate] SuryaLog cache check note: %s", e)

        if all_records:
            try:
                dt = datetime.strptime(month_str, "%Y-%m")
                month_name = dt.strftime("%B")
                year = dt.strftime("%Y")
                dt_year = dt.year
            except ValueError:
                month_name = now.strftime("%B")
                year = now.strftime("%Y")
                dt_year = now.year

            # Enrich cached records with persistent history and daily data
            try:
                from services.history import enrich_records_with_history, enrich_records_with_daily_history
                enrich_records_with_history(all_records, target_year=dt_year)
                enrich_records_with_daily_history(all_records)
            except Exception as e:
                logger.debug("Could not enrich records with history: %s", e)

            classified = classify_plants(all_records)
            update_state(
                classified=classified,
                month_name=month_name,
                year=year,
                sources=sources_found or SUPPORTED_SOURCES,
                response_data=None,
            )

            from helpers import _build_response_data
            _build_response_data()

            logger.info(
                "[Auto-Hydrate] Successfully hydrated %d plants for %s from cache across %s.",
                len(all_records),
                month_str,
                sources_found,
            )
            return True

    logger.info("[Auto-Hydrate] No fresh cached plant data found for candidates: %s.", candidate_months)
    return False


def run_auto_sync(target_month: Optional[str] = None, force_refresh: bool = True) -> Dict[str, Any]:
    """
    Execute full multi-source sync, save to disk cache and Excel, and update AppState.
    """
    if not target_month:
        target_month = datetime.now().strftime("%Y-%m")

    try:
        dt = datetime.strptime(target_month, "%Y-%m")
        month_name = dt.strftime("%B")
        year = dt.strftime("%Y")
        dt_year = dt.year
    except ValueError:
        month_name = datetime.now().strftime("%B")
        year = datetime.now().strftime("%Y")
        dt_year = datetime.now().year

    logger.info("[Auto-Sync] Starting automated sync for %s (%s %s)...", target_month, month_name, year)

    records, failed, fetch_time = fetch_from_sources(
        target_month=target_month,
        sources=SUPPORTED_SOURCES,
        force_refresh=force_refresh,
    )

    xlsx_path = None
    if records:
        try:
            from services.history import enrich_records_with_history
            enrich_records_with_history(records, target_year=dt_year)
        except Exception as e:
            logger.debug("Could not enrich records with history: %s", e)

        try:
            xlsx_path = save_fetched_data_to_excel(records, month_name, year)
        except Exception as ex:
            logger.warning("[Auto-Sync] Excel save note: %s", ex)

        classified = classify_plants(records)
        update_state(
            classified=classified,
            filepath=xlsx_path,
            month_name=month_name,
            year=year,
            sources=SUPPORTED_SOURCES,
            response_data=None,
        )

        from helpers import _build_response_data
        data, counts = _build_response_data()

        logger.info(
            "[Auto-Sync] Completed in %ds. Loaded %d plants (Active: %d, Offline: %d).",
            fetch_time,
            len(records),
            counts.get("Active", 0),
            counts.get("Offline", 0),
        )
        return {
            "success": True,
            "total_plants": len(records),
            "fetch_time": fetch_time,
            "failed": failed,
            "counts": counts,
        }
    else:
        logger.error("[Auto-Sync] Fetch returned 0 records across all sources.")
        return {
            "success": False,
            "error": "No records fetched from any source",
            "failed": failed,
        }


class SolaronScheduler:
    """
    Background daemon for scheduled daily and monthly solar fleet syncs.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_daily_sync_date: Optional[str] = None
        self._last_monthly_sync_month: Optional[str] = None

    def start(self) -> None:
        if not Config.AUTO_SYNC_ENABLED:
            logger.info("[Scheduler] Automated background sync is disabled by configuration.")
            return

        if self._thread and self._thread.is_alive():
            logger.debug("[Scheduler] Thread is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="SolaronScheduler", daemon=True)
        self._thread.start()
        logger.info("[Scheduler] Solaron background scheduler started.")

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=3)
            logger.info("[Scheduler] Solaron background scheduler stopped.")

    def _run_loop(self) -> None:
        # Initial wait to allow app to fully initialize
        self._stop_event.wait(5.0)

        # On startup, hydrate from cache immediately
        if Config.AUTO_LOAD_ON_STARTUP:
            hydrated = hydrate_state_from_cache()
            if not hydrated and Config.AUTO_FETCH_ON_STARTUP:
                logger.info("[Scheduler] No cache found on startup. Spawning initial background auto-fetch...")
                threading.Thread(target=run_auto_sync, daemon=True).start()

        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                current_month_str = now.strftime("%Y-%m")

                # 1. Daily Sync at configured hour (e.g. 19:00 IST)
                if (
                    now.hour >= Config.AUTO_SYNC_DAILY_HOUR
                    and self._last_daily_sync_date != today_str
                ):
                    logger.info("[Scheduler] Triggering scheduled daily solar fleet sync for %s...", today_str)
                    run_auto_sync(current_month_str, force_refresh=True)
                    self._last_daily_sync_date = today_str

                # 2. Monthly Closing Sync on configured day & hour (e.g. 1st of month at 01:00)
                if (
                    now.day == Config.AUTO_SYNC_MONTHLY_DAY
                    and now.hour >= Config.AUTO_SYNC_MONTHLY_HOUR
                    and self._last_monthly_sync_month != current_month_str
                ):
                    # Close out the previous month's final generation
                    prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
                    logger.info("[Scheduler] Triggering scheduled monthly closing report for %s...", prev_month)
                    run_auto_sync(prev_month, force_refresh=True)
                    self._last_monthly_sync_month = current_month_str

            except Exception as e:
                logger.exception("[Scheduler] Unexpected error in background loop: %s", e)

            # Sleep for 60 seconds before next check
            self._stop_event.wait(60.0)


scheduler = SolaronScheduler()
