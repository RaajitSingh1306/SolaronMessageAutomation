import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from services.excel import PlantRecord

logger = logging.getLogger(__name__)


def safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "" or val == "-" or val == "--":
        return default
    try:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            val_str = val.strip()
            if not val_str or val_str in ("--", "-", "null", "None"):
                return default
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", val_str.replace(",", ""))
            if m:
                return float(m.group(0))
        return default
    except (ValueError, TypeError):
        return default


class SuryaLogFetcher:
    """Fetches plant data from SuryaLog Cloud web portal using Playwright."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.username = username or Config.SURYALOG_USER
        self.password = password or Config.SURYALOG_PASSWORD
        self.base_url = (base_url or Config.SURYALOG_URL).rstrip("/")

    def fetch_all_plants(
        self,
        target_date: Optional[str] = None,
        progress_callback=None,
        limit: Optional[int] = None,
    ) -> Tuple[List[PlantRecord], List[Dict[str, Any]], int]:
        """
        Retrieves all plants from SuryaLog via Playwright.

        Returns:
            records: List of PlantRecord objects
            failed: List of dicts describing plants that failed
            fetch_time: Total fetch time in seconds
        """
        from playwright.sync_api import sync_playwright

        start_time = time.time()
        records: List[PlantRecord] = []
        failed: List[Dict[str, Any]] = []

        if not self.username or not self.password:
            logger.error("[SuryaLog] Missing username or password in config.")
            return [], [{"error": "Missing credentials"}], 0

        logger.info(f"[SuryaLog] Starting retrieval for user: {self.username}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1600, "height": 900})
                page = context.new_page()

                # 1. Login
                login_url = self.base_url
                logger.info(f"[SuryaLog] Navigating to {login_url}...")
                page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2000)

                page.fill("#loginId", self.username)
                page.fill("#password", self.password)
                page.click("#btnlogin")
                page.wait_for_timeout(6000)

                # Dismiss modals
                try:
                    page.evaluate("""() => {
                        document.querySelectorAll('.modal, .modal-backdrop, .swal2-container').forEach(e => e.remove());
                        if (typeof $ !== 'undefined') { $('body').removeClass('modal-open'); }
                    }""")
                except Exception as e:
                    logger.debug(f"[SuryaLog] Modal dismiss note: {e}")

                # 2. Get plant options from select element
                options = page.eval_on_selector_all(
                    "select option",
                    "options => options.map(o => ({text: o.text.trim(), value: o.value}))"
                )

                plant_options = [
                    opt for opt in options
                    if opt.get("text") and not opt["text"].startswith("English")
                    and not opt["text"].startswith("?")
                    and opt.get("value") and not opt["value"].startswith("http")
                ]

                logger.info(f"[SuryaLog] Found {len(plant_options)} plants in account.")

                if limit:
                    plant_options = plant_options[:limit]

                total_count = len(plant_options)

                for idx, opt in enumerate(plant_options):
                    plant_name_raw = opt["text"]
                    plant_val = opt["value"]
                    plant_name = re.sub(r"^\d+\.\s*", "", plant_name_raw).strip()

                    logger.info(f"[SuryaLog] [{idx+1}/{total_count}] Fetching '{plant_name}'...")

                    if progress_callback:
                        progress_callback(idx + 1, total_count, plant_name)

                    try:
                        # Enable select if disabled and trigger plant change via DOM
                        page.evaluate("""(val) => {
                            const sel = document.querySelector('#searchPlant') || document.querySelector('select');
                            if (sel) {
                                sel.removeAttribute('disabled');
                                sel.disabled = false;
                                sel.value = val;
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                if (typeof selectPlant === 'function') {
                                    try { selectPlant(sel); } catch(e) {}
                                }
                            }
                        }""", plant_val)
                        page.wait_for_timeout(3500)

                        page.evaluate("""() => {
                            document.querySelectorAll('.modal, .modal-backdrop, .swal2-container').forEach(e => e.remove());
                            if (typeof $ !== 'undefined') { $('body').removeClass('modal-open'); }
                        }""")

                        body_text = page.inner_text("body")

                        dc_cap = None
                        ac_cap = None
                        solar_power = None
                        day_gen = None
                        month_gen = None
                        total_gen = None
                        co2 = None
                        status = "normal"

                        m_dc = re.search(r"([\d\.]+)\s*\n\s*DC Capacity\(KWp\)", body_text, re.IGNORECASE)
                        if m_dc:
                            dc_cap = safe_float(m_dc.group(1))

                        m_ac = re.search(r"([\d\.]+)\s*\n\s*AC Capacity\(KW\)", body_text, re.IGNORECASE)
                        if m_ac:
                            ac_cap = safe_float(m_ac.group(1))

                        m_power = re.search(r"Solar Power\s*\n\s*([\d\.]+)\s*KW", body_text, re.IGNORECASE)
                        if m_power:
                            solar_power = safe_float(m_power.group(1))
                        else:
                            m_ac_p = re.search(r"([\d\.]+)\s*\n\s*AC Power\(KW\)", body_text, re.IGNORECASE)
                            if m_ac_p:
                                solar_power = safe_float(m_ac_p.group(1))

                        m_day = re.search(r"Day Gen\s*\n\s*([\d\.]+)\s*KWh", body_text, re.IGNORECASE)
                        if m_day:
                            day_gen = safe_float(m_day.group(1))

                        m_month = re.search(r"Month Gen(?:eration)?\s*\n\s*([\d\.]+)\s*(KWh|MWh)?", body_text, re.IGNORECASE)
                        if m_month:
                            val = safe_float(m_month.group(1))
                            unit = (m_month.group(2) or "").upper()
                            if unit == "MWH" and val > 0:
                                val = round(val * 1000.0, 2)
                            month_gen = val

                        m_year = re.search(r"Year Gen(?:eration)?\s*\n\s*([\d\.]+)\s*(KWh|MWh)?", body_text, re.IGNORECASE)
                        year_gen = None
                        if m_year:
                            val = safe_float(m_year.group(1))
                            unit = (m_year.group(2) or "").upper()
                            if unit == "MWH" and val > 0:
                                val = round(val * 1000.0, 2)
                            year_gen = val

                        m_total = re.search(r"Total Gen(?:eration)?\s*\n\s*([\d\.]+)\s*(KWh|MWh)?", body_text, re.IGNORECASE)
                        if m_total:
                            val = safe_float(m_total.group(1))
                            unit = (m_total.group(2) or "").upper()
                            if unit == "MWH" and val > 0:
                                val = round(val * 1000.0, 2)
                            total_gen = val

                        m_co2 = re.search(r"([\d\.]+)\s*Kg\s*\n\s*\(CO2\)", body_text, re.IGNORECASE)
                        if m_co2:
                            co2 = safe_float(m_co2.group(1))

                        if "offline" in body_text.lower() or "error" in body_text.lower():
                            if (solar_power is None or solar_power == 0) and (day_gen is None or day_gen == 0):
                                status = "offline"

                        month_energy = month_gen if month_gen is not None else 0.0
                        today_energy = day_gen if day_gen is not None else 0.0
                        total_energy = total_gen if total_gen is not None else 0.0
                        year_energy = year_gen if year_gen is not None else 0.0

                        if month_energy == 0.0 and today_energy > 0.0:
                            month_energy = today_energy

                        record = PlantRecord(
                            plant_name=plant_name,
                            energy_this_month=month_energy,
                            energy_this_year=year_energy,
                            energy_total=total_energy,
                            income_this_month=0.0,
                            income_total=0.0,
                            co2_this_month=co2 or 0.0,
                            co2_total=0.0,
                            savings=0.0,
                            message_status="",
                            nut_bolts="",
                            row_index=0,
                            source="suryalog",
                            capacity_kwp=dc_cap or ac_cap or 0.0,
                            current_power_kw=solar_power or 0.0,
                            energy_today=today_energy,
                            plant_status=status,
                            city="",
                        )
                        records.append(record)

                    except Exception as plant_err:
                        logger.warning(f"[SuryaLog] Error processing {plant_name}: {plant_err}")
                        failed.append({"plant_name": plant_name, "error": str(plant_err)})

                browser.close()
                fetch_time = int(time.time() - start_time)

                # Enrich records with persistent history if available
                try:
                    from services.history import enrich_records_with_history
                    dt_year = int(target_date.split("-")[0]) if target_date else None
                    enrich_records_with_history(records, target_year=dt_year)
                except Exception as e:
                    logger.debug("Could not enrich SuryaLog records with history: %s", e)

                logger.info(f"[SuryaLog] Completed fetch in {fetch_time}s. Total plants: {len(records)}.")
                return records, failed, fetch_time

        except Exception as e:
            logger.exception(f"[SuryaLog] Critical retrieval error: {e}")
            fetch_time = int(time.time() - start_time)
            failed.append({"error": str(e)})
            return records, failed, fetch_time

    def fetch_yearly_data(
        self, target_year: int, progress_callback=None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        """
        Fetch yearly generation stats from SuryaLog Cloud portal for each plant.
        ON-DEMAND ONLY.
        """
        records, failed, fetch_time = self.fetch_all_plants(
            target_date=f"{target_year}-01",
            progress_callback=progress_callback,
        )

        results: List[Dict[str, Any]] = []
        for r in records:
            results.append({
                "source": "suryalog",
                "plant_name": r.plant_name,
                "year": target_year,
                "yearly_total": r.energy_this_year,
                "monthly_breakdown": {},
            })

        if results:
            try:
                from services.history import merge_batch_yearly_data
                merge_batch_yearly_data(results, target_year=target_year)
            except Exception as e:
                logger.error("Failed to merge SuryaLog yearly results: %s", e)

        return results, failed, fetch_time
