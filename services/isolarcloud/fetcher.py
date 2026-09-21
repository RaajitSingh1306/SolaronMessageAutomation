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


class ISolarCloudFetcher:
    """Fetches plant data from Sungrow iSolarCloud web portal using Playwright."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.username = username or Config.ISOLARCLOUD_USER
        self.password = password or Config.ISOLARCLOUD_PASSWORD
        self.base_url = (base_url or Config.ISOLARCLOUD_URL).rstrip("/")

    def fetch_all_plants(
        self,
        target_date: Optional[str] = None,
        progress_callback=None,
        limit: Optional[int] = None,
    ) -> Tuple[List[PlantRecord], List[Dict[str, Any]], int]:
        """
        Retrieves all plants from iSolarCloud via Playwright.

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
            logger.error("[iSolarCloud] Missing username or password in config.")
            return [], [{"error": "Missing credentials"}], 0

        logger.info(f"[iSolarCloud] Starting retrieval for user: {self.username}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1600, "height": 900})
                page = context.new_page()

                # 1. Navigate to login
                login_url = f"{self.base_url}/#/login"
                logger.info(f"[iSolarCloud] Navigating to {login_url}...")
                page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)

                # Cookie / terms consent
                try:
                    agree = page.query_selector("button:has-text('Yes, I agree')") or page.query_selector("button:has-text('Agree')")
                    if agree:
                        agree.click()
                        page.wait_for_timeout(1000)
                except Exception as e:
                    logger.debug(f"[iSolarCloud] Consent dismiss note: {e}")

                acc_input = page.query_selector("input[placeholder*='Account']") or page.query_selector("input[placeholder*='Email']")
                pwd_input = page.query_selector("input[placeholder*='Password']")

                if not (acc_input and pwd_input):
                    logger.error("[iSolarCloud] Could not find login input fields.")
                    browser.close()
                    return [], [{"error": "Login fields not found"}], int(time.time() - start_time)

                acc_input.fill(self.username)
                pwd_input.fill(self.password)
                page.wait_for_timeout(500)

                login_btn = page.query_selector("button:has-text('Login')") or page.query_selector(".login-btn")
                if login_btn:
                    login_btn.click()
                else:
                    pwd_input.press("Enter")

                logger.info("[iSolarCloud] Submitted credentials. Waiting for session...")
                page.wait_for_timeout(8000)

                # 2. Navigate to plant table (#/plant)
                plant_url = f"{self.base_url}/#/plant"
                logger.info(f"[iSolarCloud] Navigating to {plant_url}...")
                page.goto(plant_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(6000)

                has_next = True
                page_num = 1

                while has_next:
                    logger.info(f"[iSolarCloud] Parsing table page {page_num}...")
                    rows = page.query_selector_all("tbody tr, .el-table__row")
                    logger.info(f"[iSolarCloud] Found {len(rows)} plant rows on page {page_num}.")

                    for r in rows:
                        try:
                            row_text = r.inner_text()
                            lines = [line.strip() for line in row_text.split("\n") if line.strip()]
                            if not lines:
                                continue

                            # Line 0: Plant name
                            plant_name = lines[0].replace("\xa0", " ").strip()

                            # Location / city
                            city = ""
                            location = lines[1] if len(lines) > 1 and "India" in lines[1] else ""
                            if location:
                                parts = [p.strip() for p in location.split(",")]
                                if len(parts) >= 2:
                                    city = parts[-2] if "India" in parts[-1] else parts[-1]

                            # Status
                            status = "normal"
                            if any("offline" in l.lower() for l in lines):
                                status = "offline"
                            elif any("fault" in l.lower() or "abnormal" in l.lower() for l in lines):
                                status = "fault"
                            elif any("normal" in l.lower() for l in lines):
                                status = "normal"

                            capacity_kwp = 0.0
                            current_power_kw = 0.0
                            energy_today_kwh = None
                            energy_month_kwh = None
                            energy_year_kwh = None
                            energy_total_kwh = None

                            for line in lines:
                                if "kWp" in line:
                                    capacity_kwp = safe_float(line)
                                elif line.endswith(" kW") or line.endswith(" W"):
                                    if line.endswith(" W") and not line.endswith(" kW"):
                                        val = safe_float(line)
                                        current_power_kw = round(val / 1000.0, 3)
                                    else:
                                        current_power_kw = safe_float(line)
                                elif "kWh" in line or "MWh" in line:
                                    val = safe_float(line)
                                    if "MWh" in line and val > 0:
                                        val = round(val * 1000.0, 2)
                                    if energy_today_kwh is None:
                                        energy_today_kwh = val
                                    elif energy_month_kwh is None:
                                        energy_month_kwh = val
                                    elif energy_year_kwh is None:
                                        energy_year_kwh = val
                                    elif energy_total_kwh is None:
                                        energy_total_kwh = val

                            # If only 3 energy values were detected: today, month, total
                            if energy_total_kwh is None and energy_year_kwh is not None:
                                energy_total_kwh = energy_year_kwh
                                energy_year_kwh = None

                            month_energy = energy_month_kwh if energy_month_kwh is not None else 0.0
                            today_energy = energy_today_kwh if energy_today_kwh is not None else 0.0
                            total_energy = energy_total_kwh if energy_total_kwh is not None else 0.0
                            year_energy = energy_year_kwh if energy_year_kwh is not None else 0.0

                            # If month energy is 0, at least check if today had energy
                            if month_energy == 0.0 and today_energy > 0.0:
                                month_energy = today_energy

                            record = PlantRecord(
                                plant_name=plant_name,
                                energy_this_month=month_energy,
                                energy_this_year=year_energy,
                                energy_total=total_energy,
                                income_this_month=0.0,
                                income_total=0.0,
                                co2_this_month=0.0,
                                co2_total=0.0,
                                savings=0.0,
                                message_status="",
                                nut_bolts="",
                                row_index=0,
                                source="isolarcloud",
                                capacity_kwp=capacity_kwp,
                                current_power_kw=current_power_kw,
                                energy_today=today_energy,
                                plant_status=status,
                                city=city,
                            )
                            records.append(record)

                            if progress_callback:
                                progress_callback(len(records), len(records), plant_name)

                            if limit and len(records) >= limit:
                                break
                        except Exception as row_err:
                            logger.warning(f"[iSolarCloud] Error parsing row: {row_err}")
                            failed.append({"plant_name": "unknown", "error": str(row_err)})

                    if limit and len(records) >= limit:
                        break

                    # Dismiss any overlay dialogs
                    page.evaluate("""() => {
                        document.querySelectorAll('.el-overlay, .el-dialog__wrapper, .v-modal').forEach(e => e.remove());
                    }""")

                    # Click next page via JS
                    has_more = page.evaluate("""() => {
                        const btn = document.querySelector('button.btn-next, .btn-next');
                        if (btn && !btn.disabled && !btn.classList.contains('is-disabled')) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }""")

                    if has_more:
                        logger.info("[iSolarCloud] Moving to next page...")
                        page.wait_for_timeout(4000)
                        page_num += 1
                    else:
                        has_next = False

                browser.close()
                fetch_time = int(time.time() - start_time)

                # Enrich records with persistent history if available
                try:
                    from services.history import enrich_records_with_history
                    dt_year = int(target_date.split("-")[0]) if target_date else None
                    enrich_records_with_history(records, target_year=dt_year)
                except Exception as e:
                    logger.debug("Could not enrich iSolarCloud records with history: %s", e)

                logger.info(f"[iSolarCloud] Completed fetch in {fetch_time}s. Total plants: {len(records)}.")
                return records, failed, fetch_time

        except Exception as e:
            logger.exception(f"[iSolarCloud] Critical retrieval error: {e}")
            fetch_time = int(time.time() - start_time)
            failed.append({"error": str(e)})
            return records, failed, fetch_time

    def fetch_yearly_data(
        self, target_year: int, progress_callback=None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        """
        Fetch yearly generation stats from iSolarCloud portal.
        ON-DEMAND ONLY.
        """
        records, failed, fetch_time = self.fetch_all_plants(
            target_date=f"{target_year}-01",
            progress_callback=progress_callback,
        )

        results: List[Dict[str, Any]] = []
        for r in records:
            results.append({
                "source": "isolarcloud",
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
                logger.error("Failed to merge iSolarCloud yearly results: %s", e)

        return results, failed, fetch_time
