import datetime
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from requests.exceptions import ConnectionError as RequestsConnectionError

import growattServer

from config import Config
from services.excel import PlantRecord

logger = logging.getLogger(__name__)


def _parse_energy_to_kwh(val: Any) -> float:
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().upper()
    multiplier = 1.0
    if "MWH" in val_str:
        multiplier = 1000.0
    elif "GWH" in val_str:
        multiplier = 1000000.0

    match = re.search(r"([\d\.]+)", val_str)
    if match:
        return float(match.group(1)) * multiplier
    return 0.0


class GrowattFetcher:
    """Fetches plant data from Growatt ShineServer API."""

    def __init__(self, username: str, password: str, server_url: str):
        self.username = username
        self.password = password
        self.api = growattServer.GrowattApi()
        if server_url:
            self.api.server_url = server_url
        self.user_id = None

    def login(self) -> bool:
        """Authenticate and return True if successful."""
        try:
            response = self.api.login(self.username, self.password)
            if response.get("success") and "user" in response:
                self.user_id = response["user"]["id"]
                logger.info("Growatt login successful. User ID: %s", self.user_id)
                return True
            else:
                logger.error(
                    "Growatt login failed: %s", response.get("msg", "Unknown error")
                )
                return False
        except Exception as e:
            logger.exception("Growatt login exception: %s", e)
            return False

    def fetch_all_plants(
        self, target_date: str, progress_callback=None
    ) -> Tuple[List[PlantRecord], List[Dict[str, Any]], int]:
        """
        Fetch all plants and their monthly energy data.

        Args:
            target_date: Format "YYYY-MM" (e.g. "2026-08")

        Returns:
            records: List of PlantRecord objects
            failed: List of dicts describing plants that failed to fetch completely
            total_time: Total fetch time in seconds
        """
        if not self.user_id:
            if not self.login():
                raise Exception("Failed to authenticate with Growatt")

        start_time = time.time()
        records: List[PlantRecord] = []
        failed: List[Dict[str, Any]] = []

        logger.info("Fetching plant list...")
        try:
            plants_info = self.api.plant_list(self.user_id)
            # Handle if the API returned a paginated dict instead of a flat list
            if isinstance(plants_info, dict):
                plants_info = (
                    plants_info.get("data")
                    or plants_info.get("list")
                    or plants_info.get("back")
                    or []
                )
        except Exception as e:
            logger.exception("Failed to fetch plant list: %s", e)
            raise

        logger.info("Found %d plants. Beginning detailed fetch...", len(plants_info))

        # For writing to Excel, row_index starts at 7 (1-based Excel row, since headers are at row 6)
        # This matches the SolarOn format which has 5 metadata rows + 1 header row above the data.
        excel_data_start = 7

        # Retry configuration for transient network errors
        MAX_RETRIES = 3
        RETRY_BACKOFF = [5, 15, 45]  # seconds to wait before each retry attempt

        for idx, plant_data in enumerate(plants_info):
            # Growatt API inconsistently uses 'id' or 'plantId'
            plant_id = plant_data.get("plantId") or plant_data.get("id")
            plant_name = plant_data.get("plantName") or plant_data.get(
                "name", "Unknown"
            )

            if progress_callback:
                progress_callback(idx + 1, len(plants_info), plant_name)

            last_error: Optional[Exception] = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    if attempt > 0:
                        wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                        logger.warning(
                            "Retry %d/%d for %s in %ds...",
                            attempt,
                            MAX_RETRIES,
                            plant_name,
                            wait,
                        )
                        time.sleep(wait)
                        # Re-authenticate on connection errors to get a fresh session
                        if not self.login():
                            logger.error("Re-login failed, skipping %s", plant_name)
                            break

                    logger.debug(
                        "Fetching monthly data for %s (ID: %s)", plant_name, plant_id
                    )

                    # Parse target_date (YYYY-MM) to datetime object
                    dt = datetime.datetime.strptime(target_date, "%Y-%m")

                    # Fetch monthly detail
                    detail_response = self.api.plant_detail(
                        plant_id, growattServer.Timespan.month, dt
                    )

                    monthly_energy = 0.0
                    daily_history = {}
                    income_this_month = 0.0

                    if isinstance(detail_response, dict):
                        # Check for daily breakdown in detail_response["data"] or detail_response["plantData"]["data"]
                        day_data = detail_response.get("data")
                        if not isinstance(day_data, dict):
                            day_data = detail_response.get("plantData", {}).get("data")

                        if isinstance(day_data, dict) and day_data:
                            valid_days = {}
                            for d_key, d_val in day_data.items():
                                if d_val and str(d_key).isdigit():
                                    kwh = _parse_energy_to_kwh(d_val)
                                    valid_days[f"{target_date}-{int(d_key):02d}"] = kwh
                            if valid_days:
                                daily_history = valid_days
                                monthly_energy = round(sum(valid_days.values()), 2)
                            elif "currentMonthEnergy" in day_data:
                                monthly_energy = _parse_energy_to_kwh(
                                    day_data.get("currentMonthEnergy", 0.0)
                                )

                        # Fallback to plantData["currentEnergy"] (e.g. "1.21 MWh" or "691.4 kWh")
                        plant_data_resp = detail_response.get("plantData")
                        if isinstance(plant_data_resp, dict):
                            if not monthly_energy:
                                monthly_energy = _parse_energy_to_kwh(
                                    plant_data_resp.get("currentEnergy", 0.0)
                                )
                            income_text = plant_data_resp.get("plantMoneyText") or plant_data_resp.get("plantMoney", 0.0)
                            if income_text:
                                income_this_month = _parse_energy_to_kwh(income_text)

                    # Fetch total energy from the plant list response
                    total_energy = _parse_energy_to_kwh(
                        plant_data.get("totalEnergy", 0.0)
                        or plant_data.get("total_energy", 0.0)
                    )

                    today_energy = _parse_energy_to_kwh(
                        plant_data.get("todayEnergy", 0.0)
                        or plant_data.get("today_energy", 0.0)
                    )

                    # NOTE: Never overwrite monthly_energy with today_energy!
                    # today_energy represents a single-day snapshot, not the month.

                    nom_power = _parse_energy_to_kwh(
                        plant_data.get("nominal_Power", 0.0)
                        or plant_data.get("nominalPower", 0.0)
                    )
                    cap_kwp = round(nom_power / 1000.0, 2) if nom_power > 1000 else round(nom_power, 2)
                    cur_power = _parse_energy_to_kwh(
                        plant_data.get("currentPac", 0.0)
                        or plant_data.get("currentPower", 0.0)
                    )
                    city = str(plant_data.get("city", "") or "")

                    # Construct PlantRecord
                    record = PlantRecord(
                        plant_name=plant_name,
                        energy_this_month=monthly_energy,
                        energy_this_year=0.0,
                        energy_total=total_energy,
                        income_this_month=income_this_month,
                        income_total=0.0,
                        co2_this_month=round(monthly_energy * 0.82, 1) if monthly_energy > 0 else 0.0,
                        co2_total=0.0,
                        savings=income_this_month if income_this_month > 0 else round(monthly_energy * Config.PRICE_PER_UNIT, 2),
                        message_status="",
                        nut_bolts="",
                        row_index=excel_data_start + idx,
                        source="growatt",
                        capacity_kwp=cap_kwp,
                        current_power_kw=cur_power,
                        energy_today=today_energy,
                        city=city,
                        daily_history=daily_history,
                    )
                    records.append(record)
                    last_error = None
                    break  # success — exit retry loop

                except (RequestsConnectionError, OSError) as e:
                    # Transient network/DNS error — worth retrying
                    last_error = e
                    logger.warning(
                        "Network error for %s (attempt %d/%d): %s",
                        plant_name,
                        attempt + 1,
                        MAX_RETRIES + 1,
                        e,
                    )

                except Exception as e:
                    # Non-retryable error (e.g. bad API response) — fail immediately
                    last_error = e
                    logger.error(
                        "Non-retryable error for %s: %s", plant_name, e
                    )
                    break

            if last_error is not None:
                logger.error(
                    "Failed to fetch details for %s after %d attempts: %s",
                    plant_name,
                    MAX_RETRIES + 1,
                    last_error,
                )
                failed.append(
                    {"plant_id": plant_id, "plant_name": plant_name, "error": str(last_error)}
                )

            # Rate limiting delay
            time.sleep(Config.GROWATT_FETCH_DELAY)

        end_time = time.time()
        fetch_time = int(end_time - start_time)

        # Enrich records with persistent history if available
        try:
            from services.history import enrich_records_with_history
            dt_year = datetime.datetime.strptime(target_date, "%Y-%m").year
            enrich_records_with_history(records, target_year=dt_year)
        except Exception as e:
            logger.debug("Could not enrich records with history: %s", e)

        logger.info(
            "Fetch complete in %ds. Successfully fetched %d/%d.",
            fetch_time,
            len(records),
            len(plants_info),
        )
        return records, failed, fetch_time

    def fetch_yearly_data(
        self, target_year: int, progress_callback=None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        """
        Fetch yearly breakdown and historical generation for all Growatt plants.
        Fetches 12-month breakdown for target_year and target_year - 1.
        ON-DEMAND ONLY.
        """
        if not self.user_id:
            if not self.login():
                raise Exception("Failed to authenticate with Growatt")

        start_time = time.time()
        results: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        logger.info("[Growatt] Starting ON-DEMAND yearly history fetch for year %d...", target_year)
        try:
            plants_info = self.api.plant_list(self.user_id)
            if isinstance(plants_info, dict):
                plants_info = (
                    plants_info.get("data")
                    or plants_info.get("list")
                    or plants_info.get("back")
                    or []
                )
        except Exception as e:
            logger.exception("Failed to fetch plant list for yearly history: %s", e)
            raise

        total_plants = len(plants_info)
        logger.info("[Growatt] Found %d plants for yearly fetch.", total_plants)

        for idx, plant_data in enumerate(plants_info):
            plant_id = plant_data.get("plantId") or plant_data.get("id")
            plant_name = plant_data.get("plantName") or plant_data.get("name", "Unknown")

            if progress_callback:
                progress_callback(idx + 1, total_plants, f"[Growatt] {plant_name}")

            try:
                # 1. Fetch target_year breakdown (e.g. 2026)
                dt_curr = datetime.datetime(target_year, 1, 1)
                curr_resp = self.api.plant_detail(plant_id, growattServer.Timespan.year, dt_curr)
                curr_breakdown = {}
                curr_total = 0.0

                if "data" in curr_resp and isinstance(curr_resp["data"], dict):
                    curr_total = _parse_energy_to_kwh(curr_resp["data"].get("yearEnergy", 0.0))

                if "plantData" in curr_resp and "data" in curr_resp["plantData"]:
                    m_data = curr_resp["plantData"]["data"]
                    if isinstance(m_data, dict):
                        for m_k, m_v in m_data.items():
                            val = _parse_energy_to_kwh(m_v)
                            # m_k could be "1", "2", "2026-01", etc.
                            m_num = m_k.split("-")[-1] if "-" in str(m_k) else str(m_k)
                            if m_num.isdigit():
                                curr_breakdown[f"{int(m_num):02d}"] = val
                        if not curr_total:
                            curr_total = sum(curr_breakdown.values())

                time.sleep(Config.GROWATT_FETCH_DELAY)

                # 2. Fetch last_year breakdown (e.g. 2025)
                dt_last = datetime.datetime(target_year - 1, 1, 1)
                last_resp = self.api.plant_detail(plant_id, growattServer.Timespan.year, dt_last)
                last_breakdown = {}
                last_total = 0.0

                if "data" in last_resp and isinstance(last_resp["data"], dict):
                    last_total = _parse_energy_to_kwh(last_resp["data"].get("yearEnergy", 0.0))

                if "plantData" in last_resp and "data" in last_resp["plantData"]:
                    m_data_last = last_resp["plantData"]["data"]
                    if isinstance(m_data_last, dict):
                        for m_k, m_v in m_data_last.items():
                            val = _parse_energy_to_kwh(m_v)
                            m_num = m_k.split("-")[-1] if "-" in str(m_k) else str(m_k)
                            if m_num.isdigit():
                                last_breakdown[f"{int(m_num):02d}"] = val
                        if not last_total:
                            last_total = sum(last_breakdown.values())

                results.append({
                    "source": "growatt",
                    "plant_name": plant_name,
                    "plant_id": plant_id,
                    "year": target_year,
                    "monthly_breakdown": curr_breakdown,
                    "yearly_total": round(curr_total, 2),
                    "last_year_breakdown": last_breakdown,
                    "last_year_total": round(last_total, 2),
                })

            except Exception as ex:
                logger.warning("[Growatt] Error fetching yearly for %s: %s", plant_name, ex)
                failed.append({"plant_id": plant_id, "plant_name": plant_name, "error": str(ex)})

            time.sleep(Config.GROWATT_FETCH_DELAY)

        # Batch merge into persistent history
        if results:
            try:
                from services.history import merge_batch_yearly_data
                merge_batch_yearly_data(results, target_year=target_year)
            except Exception as e:
                logger.error("Failed to merge yearly results into history: %s", e)

        fetch_time = int(time.time() - start_time)
        logger.info("[Growatt] Completed yearly history fetch for %d plants in %ds.", len(results), fetch_time)
        return results, failed, fetch_time
