import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import Config
from services.excel import PlantRecord
from services.growatt import (
    GrowattFetcher,
    get_cached_data as get_growatt_cache,
    save_to_cache as save_growatt_cache,
)
from services.isolarcloud import (
    ISolarCloudFetcher,
    get_cached_data as get_isolar_cache,
    save_to_cache as save_isolar_cache,
)
from services.suryalog import (
    SuryaLogFetcher,
    get_cached_data as get_suryalog_cache,
    save_to_cache as save_suryalog_cache,
)

logger = logging.getLogger(__name__)

SUPPORTED_SOURCES = ["growatt", "isolarcloud", "suryalog"]


def fetch_from_sources(
    target_month: str,
    sources: Optional[List[str]] = None,
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[List[PlantRecord], List[Dict[str, Any]], int]:
    """
    Fetch plant data from multiple sources with error isolation.

    Args:
        target_month: Format "YYYY-MM" (e.g. "2026-08")
        sources: List of sources to fetch from (defaults to all supported)
        force_refresh: If True, bypass cache
        progress_callback: Optional callback for overall progress (current, total, msg)
        cancel_check: Optional callback returning True if fetch should abort

    Returns:
        records: Combined list of PlantRecord objects
        failed: List of errors per source
        total_time: Total execution time in seconds
    """
    start_time = time.time()
    all_records: List[PlantRecord] = []
    failed: List[Dict[str, Any]] = []

    active_sources = [s.lower().strip() for s in (sources or SUPPORTED_SOURCES) if s.lower().strip() in SUPPORTED_SOURCES]
    if not active_sources:
        active_sources = SUPPORTED_SOURCES

    logger.info("Starting multi-source fetch for month %s across sources: %s", target_month, active_sources)

    total_sources = len(active_sources)

    for src_idx, source in enumerate(active_sources):
        if cancel_check and cancel_check():
            logger.info("Fetch aborted before source %s due to cancellation.", source)
            break

        src_start_idx = len(all_records)
        source_label = source.capitalize()

        if progress_callback:
            progress_callback(
                src_idx + 1,
                total_sources,
                f"[{source_label}] Checking cache or connecting...",
            )

        # ------------------ GROWATT ------------------
        if source == "growatt":
            try:
                cached = None if force_refresh else get_growatt_cache(target_month)
                if cached:
                    records, meta = cached
                    all_records.extend(records)
                    logger.info("[Growatt] Loaded %d plants from cache.", len(records))
                else:
                    fetcher = GrowattFetcher(
                        username=Config.GROWATT_USER,
                        password=Config.GROWATT_PASSWORD,
                        server_url=Config.GROWATT_SERVER_URL,
                    )
                    def gw_prog(curr, tot, plant):
                        if progress_callback:
                            progress_callback(src_idx + 1, total_sources, f"[Growatt] ({curr}/{tot}) {plant}")

                    records, gw_failed, _ = fetcher.fetch_all_plants(
                        target_date=target_month,
                        progress_callback=gw_prog,
                    )
                    if records:
                        save_growatt_cache(target_month, records)
                        all_records.extend(records)
                    if gw_failed:
                        failed.extend([{"source": "growatt", **f} for f in gw_failed])
            except Exception as e:
                logger.exception("[Growatt] Fetch error: %s", e)
                failed.append({"source": "growatt", "error": str(e)})

        # ------------------ ISOLARCLOUD ------------------
        elif source == "isolarcloud":
            try:
                cached = None if force_refresh else get_isolar_cache(target_month)
                if cached:
                    records, meta = cached
                    all_records.extend(records)
                    logger.info("[iSolarCloud] Loaded %d plants from cache.", len(records))
                else:
                    fetcher = ISolarCloudFetcher()
                    def isc_prog(curr, tot, plant):
                        if progress_callback:
                            progress_callback(src_idx + 1, total_sources, f"[iSolarCloud] ({curr}) {plant}")

                    records, isc_failed, _ = fetcher.fetch_all_plants(
                        target_date=target_month,
                        progress_callback=isc_prog,
                    )
                    if records:
                        save_isolar_cache(target_month, records)
                        all_records.extend(records)
                    if isc_failed:
                        failed.extend([{"source": "isolarcloud", **f} for f in isc_failed])
            except Exception as e:
                logger.exception("[iSolarCloud] Fetch error: %s", e)
                failed.append({"source": "isolarcloud", "error": str(e)})

        # ------------------ SURYALOG ------------------
        elif source == "suryalog":
            try:
                cached = None if force_refresh else get_suryalog_cache(target_month)
                if cached:
                    records, meta = cached
                    all_records.extend(records)
                    logger.info("[SuryaLog] Loaded %d plants from cache.", len(records))
                else:
                    fetcher = SuryaLogFetcher()
                    def sl_prog(curr, tot, plant):
                        if progress_callback:
                            progress_callback(src_idx + 1, total_sources, f"[SuryaLog] ({curr}/{tot}) {plant}")

                    records, sl_failed, _ = fetcher.fetch_all_plants(
                        target_date=target_month,
                        progress_callback=sl_prog,
                    )
                    if records:
                        save_suryalog_cache(target_month, records)
                        all_records.extend(records)
                    if sl_failed:
                        failed.extend([{"source": "suryalog", **f} for f in sl_failed])
            except Exception as e:
                logger.exception("[SuryaLog] Fetch error: %s", e)
                failed.append({"source": "suryalog", "error": str(e)})

    total_time = int(time.time() - start_time)
    logger.info(
        "Multi-source fetch completed in %ds: %d plants loaded, %d errors across sources.",
        total_time,
        len(all_records),
        len(failed),
    )
    return all_records, failed, total_time


def fetch_yearly_from_sources(
    target_year: int,
    sources: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """
    Orchestrate on-demand yearly generation fetch across requested sources.
    Fetches monthly breakdown for target_year and target_year - 1, and older year totals.
    """
    start_time = time.time()
    all_results: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    active_sources = [s.lower().strip() for s in (sources or SUPPORTED_SOURCES) if s.lower().strip() in SUPPORTED_SOURCES]
    if not active_sources:
        active_sources = SUPPORTED_SOURCES

    logger.info("Starting ON-DEMAND multi-source yearly fetch for year %d across sources: %s", target_year, active_sources)
    total_sources = len(active_sources)

    for src_idx, source in enumerate(active_sources):
        source_label = source.capitalize()
        if progress_callback:
            progress_callback(src_idx + 1, total_sources, f"[{source_label}] Connecting for yearly history...")

        if source == "growatt":
            try:
                fetcher = GrowattFetcher(
                    username=Config.GROWATT_USER,
                    password=Config.GROWATT_PASSWORD,
                    server_url=Config.GROWATT_SERVER_URL,
                )
                def gw_prog(curr, tot, plant):
                    if progress_callback:
                        progress_callback(src_idx + 1, total_sources, f"[Growatt] ({curr}/{tot}) {plant}")

                results, gw_failed, _ = fetcher.fetch_yearly_data(
                    target_year=target_year,
                    progress_callback=gw_prog,
                )
                if results:
                    all_results.extend(results)
                if gw_failed:
                    failed.extend([{"source": "growatt", **f} for f in gw_failed])
            except Exception as e:
                logger.exception("[Growatt] Yearly fetch error: %s", e)
                failed.append({"source": "growatt", "error": str(e)})

        elif source == "isolarcloud":
            try:
                fetcher = ISolarCloudFetcher()
                def isc_prog(curr, tot, plant):
                    if progress_callback:
                        progress_callback(src_idx + 1, total_sources, f"[iSolarCloud] ({curr}) {plant}")

                results, isc_failed, _ = fetcher.fetch_yearly_data(
                    target_year=target_year,
                    progress_callback=isc_prog,
                )
                if results:
                    all_results.extend(results)
                if isc_failed:
                    failed.extend([{"source": "isolarcloud", **f} for f in isc_failed])
            except Exception as e:
                logger.exception("[iSolarCloud] Yearly fetch error: %s", e)
                failed.append({"source": "isolarcloud", "error": str(e)})

        elif source == "suryalog":
            try:
                fetcher = SuryaLogFetcher()
                def sl_prog(curr, tot, plant):
                    if progress_callback:
                        progress_callback(src_idx + 1, total_sources, f"[SuryaLog] ({curr}) {plant}")

                results, sl_failed, _ = fetcher.fetch_yearly_data(
                    target_year=target_year,
                    progress_callback=sl_prog,
                )
                if results:
                    all_results.extend(results)
                if sl_failed:
                    failed.extend([{"source": "suryalog", **f} for f in sl_failed])
            except Exception as e:
                logger.exception("[SuryaLog] Yearly fetch error: %s", e)
                failed.append({"source": "suryalog", "error": str(e)})

    total_time = int(time.time() - start_time)
    logger.info(
        "Multi-source yearly fetch completed in %ds: %d plant histories updated, %d errors.",
        total_time,
        len(all_results),
        len(failed),
    )
    return all_results, failed, total_time
