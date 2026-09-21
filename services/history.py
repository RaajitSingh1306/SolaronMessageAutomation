"""
services/history.py

Manages persistent yearly generation history.
Stores:
- 12-month breakdown for current and previous years (e.g. 2026, 2025)
- Yearly sums for older years (2024 and earlier)

Data format is flat and normalized to enable direct SQL migration later:
{
  "fetched_at": "ISO-8601",
  "plants": {
    "growatt:Shailendra Dhomne": {
      "plant_name": "Shailendra Dhomne",
      "source": "growatt",
      "monthly_breakdown": {
        "2026": {"01": 120.5, ...},
        "2025": {"01": 110.0, ...}
      },
      "yearly_totals": {
        "2026": 1093.6,
        "2025": 1468.0,
        "2024": 1450.0
      }
    }
  }
}
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import Config
from services.excel import PlantRecord

logger = logging.getLogger(__name__)

_history_lock = threading.Lock()


def get_history_file_path() -> str:
    """Return path to yearly history JSON storage."""
    history_dir = getattr(Config, "HISTORY_DIR", os.path.join(Config.DATA_FOLDER, "history"))
    os.makedirs(history_dir, exist_ok=True)
    return os.path.join(history_dir, "yearly_data.json")


def load_history() -> Dict[str, Any]:
    """Load persistent history from database."""
    from database import SessionLocal
    from models import DailyGeneration
    db = SessionLocal()
    try:
        records = db.query(DailyGeneration).all()
        plants_dict = {}
        for r in records:
            key = f"{r.platform}:{r.plant_name}"
            plants_dict[key] = json.loads(r.history_json) if r.history_json else {}
        return {"fetched_at": datetime.now().isoformat(), "plants": plants_dict}
    except Exception as e:
        logger.error("Failed to load history from DB: %s", e)
        return {"fetched_at": None, "plants": {}}
    finally:
        db.close()


def save_history(history_data: Dict[str, Any]) -> bool:
    """Persist history data to database."""
    from database import SessionLocal
    from models import DailyGeneration
    db = SessionLocal()
    try:
        plants_dict = history_data.get("plants", {})
        
        # Load existing to minimize queries
        existing = {(r.platform, r.plant_name): r for r in db.query(DailyGeneration).all()}
        
        for key, plant_data in plants_dict.items():
            source = plant_data.get("source", "unknown")
            plant_name = plant_data.get("plant_name", "unknown")
            
            records_json = json.dumps(plant_data, ensure_ascii=False)
            if (source, plant_name) in existing:
                existing[(source, plant_name)].history_json = records_json
                existing[(source, plant_name)].fetched_at = datetime.now(timezone.utc)
            else:
                db.add(DailyGeneration(
                    platform=source,
                    plant_name=plant_name,
                    history_json=records_json
                ))
        db.commit()
        return True
    except Exception as e:
        logger.error("Failed to save history to DB: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


def _normalize_plant_key(source: str, plant_name: str) -> str:
    """Generate consistent composite key."""
    return f"{source.lower().strip()}:{plant_name.strip()}"


def merge_yearly_plant_data(
    source: str,
    plant_name: str,
    year: int,
    monthly_breakdown: Optional[Dict[str, float]] = None,
    yearly_total: Optional[float] = None,
    history_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge a single plant's yearly data into history.
    If year is current or last year (e.g. >= 2025), store monthly breakdown.
    For older years, store yearly total.
    """
    if history_data is None:
        history_data = load_history()

    plants = history_data.setdefault("plants", {})
    key = _normalize_plant_key(source, plant_name)

    current_year = datetime.now().year
    is_detailed_year = year >= (current_year - 1)  # e.g. 2025 and 2026

    if key not in plants:
        plants[key] = {
            "plant_name": plant_name,
            "source": source.lower().strip(),
            "monthly_breakdown": {},
            "yearly_totals": {},
        }

    plant_entry = plants[key]
    year_str = str(year)

    if is_detailed_year and monthly_breakdown:
        # Save monthly breakdown
        existing_breakdown = plant_entry.setdefault("monthly_breakdown", {}).setdefault(year_str, {})
        for m_str, val in monthly_breakdown.items():
            if val is not None and val >= 0:
                # Format month key as 2-digit string e.g. "01"
                m_key = f"{int(m_str):02d}" if str(m_str).isdigit() else str(m_str)
                existing_breakdown[m_key] = round(float(val), 2)

        # Calculate or set yearly total from sum of breakdown
        calc_total = sum(existing_breakdown.values())
        if yearly_total is None or yearly_total == 0.0:
            yearly_total = calc_total
        plant_entry.setdefault("yearly_totals", {})[year_str] = round(max(float(yearly_total), calc_total), 2)
    else:
        # Older year or sum only
        if yearly_total is not None and yearly_total >= 0:
            plant_entry.setdefault("yearly_totals", {})[year_str] = round(float(yearly_total), 2)

    return history_data


def merge_batch_yearly_data(
    yearly_results: List[Dict[str, Any]],
    target_year: int,
) -> bool:
    """
    Batch merge list of plant yearly data into persistent history.
    Each item in yearly_results:
    {
      "source": "growatt",
      "plant_name": "ABC",
      "year": 2026,
      "monthly_breakdown": {"01": 120.5, ...},
      "yearly_total": 1093.6,
      "older_years": {"2024": 1450.0, ...} # optional
    }
    """
    history = load_history()
    for item in yearly_results:
        src = item.get("source", "growatt")
        pname = item.get("plant_name", "")
        if not pname:
            continue
        yr = item.get("year", target_year)
        breakdown = item.get("monthly_breakdown")
        total = item.get("yearly_total")
        merge_yearly_plant_data(src, pname, yr, breakdown, total, history)

        # Also merge previous year breakdown if provided in item
        last_year = yr - 1
        last_year_breakdown = item.get("last_year_breakdown")
        last_year_total = item.get("last_year_total")
        if last_year_breakdown or last_year_total is not None:
            merge_yearly_plant_data(src, pname, last_year, last_year_breakdown, last_year_total, history)

        # Merge any older years
        older = item.get("older_years", {})
        for old_yr, old_tot in older.items():
            try:
                merge_yearly_plant_data(src, pname, int(old_yr), None, float(old_tot), history)
            except (ValueError, TypeError):
                pass

    return save_history(history)


def enrich_records_with_history(
    records: List[PlantRecord],
    target_year: Optional[int] = None,
    target_month: Optional[str] = None,
) -> None:
    """
    Attach yearly totals and monthly breakdowns from persistent history to PlantRecords.
    """
    if not records:
        return

    if target_year is None:
        if target_month:
            try:
                target_year = int(target_month.split("-")[0])
            except Exception:
                target_year = datetime.now().year
        else:
            target_year = datetime.now().year

    history = load_history()
    plants = history.get("plants", {})
    year_str = str(target_year)

    for r in records:
        key = _normalize_plant_key(getattr(r, "source", "growatt"), r.plant_name)
        plant_entry = plants.get(key)
        if not plant_entry:
            # Also try matching by name only if source prefix differs
            for p_k, p_v in plants.items():
                if p_k.endswith(f":{r.plant_name.strip()}"):
                    plant_entry = p_v
                    break

        if plant_entry:
            totals = plant_entry.get("yearly_totals", {})
            breakdowns = plant_entry.get("monthly_breakdown", {})

            # 1. Attach yearly total for target year
            hist_year_energy = totals.get(year_str, 0.0)
            if hist_year_energy > 0:
                r.energy_this_year = hist_year_energy
            elif r.energy_this_year == 0.0 and year_str in breakdowns:
                # Sum from breakdown
                sum_bd = sum(breakdowns[year_str].values())
                if sum_bd > 0:
                    r.energy_this_year = round(sum_bd, 2)

            # 2. Attach breakdown and all yearly history
            r.yearly_breakdown = breakdowns.get(year_str, {})
            r.yearly_history = totals


_cached_daily_map: Optional[Dict[str, Dict[str, float]]] = None


def load_daily_generation_map() -> Dict[str, Dict[str, float]]:
    """
    Load date-indexed daily generation records from Dashboard2 analytics db or parquet.
    Returns: {normalized_plant_name: {date_str: energy_kwh}}
    """
    global _cached_daily_map
    if _cached_daily_map is not None:
        return _cached_daily_map

    daily_map: Dict[str, Dict[str, float]] = {}

    # Candidate locations for solar_analytics.db / parquet
    possible_db_paths = [
        os.path.abspath(os.path.join(Config.BASE_DIR, "..", "Dashboard2", "data", "solar_analytics.db")),
        r"C:\Users\raaji\Downloads\Solaron\Dashboard2\data\solar_analytics.db",
        os.path.join(Config.DATA_FOLDER, "solar_analytics.db"),
    ]

    for db_path in possible_db_paths:
        if os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT date, plant_name, energy_kwh FROM daily_generation ORDER BY date DESC")
                rows = cursor.fetchall()
                for dt, name, kwh in rows:
                    p_key = name.strip().lower()
                    daily_map.setdefault(p_key, {})[dt] = round(float(kwh or 0.0), 2)
                conn.close()
                logger.info("Loaded %d daily generation plant records from %s", len(daily_map), db_path)
                break
            except Exception as e:
                logger.warning("Failed reading daily records from %s: %s", db_path, e)

    # Fallback to parquet if DB was not loaded
    if not daily_map:
        possible_parquet = [
            os.path.abspath(os.path.join(Config.BASE_DIR, "..", "Dashboard2", "data", "processed", "daily_generation.parquet")),
            r"C:\Users\raaji\Downloads\Solaron\Dashboard2\data\processed\daily_generation.parquet",
        ]
        for p_path in possible_parquet:
            if os.path.exists(p_path):
                try:
                    import pandas as pd
                    df = pd.read_parquet(p_path)
                    for _, row in df.iterrows():
                        p_key = str(row["plant_name"]).strip().lower()
                        dt = str(row["date"])
                        kwh = round(float(row.get("energy_kwh", 0.0) or 0.0), 2)
                        daily_map.setdefault(p_key, {})[dt] = kwh
                    logger.info("Loaded %d daily generation plant records from parquet %s", len(daily_map), p_path)
                    break
                except Exception as e:
                    logger.warning("Failed reading parquet %s: %s", p_path, e)

    _cached_daily_map = daily_map
    return daily_map


def enrich_records_with_daily_history(
    records: List[PlantRecord],
    target_date: Optional[str] = None,
) -> None:
    """
    Populate PlantRecord objects with:
    - daily_history: {date: energy_kwh}
    - energy_yesterday: generation for yesterday or most recent available date
    - energy_weekly: rolling 7-day actual sum
    """
    if not records:
        return

    daily_map = load_daily_generation_map()
    now = datetime.now()
    cur_date_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now.replace(day=now.day - 1) if now.day > 1 else now).strftime("%Y-%m-%d")

    for r in records:
        p_key = r.plant_name.strip().lower()
        hist = daily_map.get(p_key, {})

        if not hist:
            # Try partial/fuzzy match
            for k, v in daily_map.items():
                if k in p_key or p_key in k:
                    hist = v
                    break

        r.daily_history = hist

        # 1. Resolve energy_yesterday
        if hist:
            sorted_dates = sorted(hist.keys(), reverse=True)
            if yesterday_str in hist:
                r.energy_yesterday = hist[yesterday_str]
            elif len(sorted_dates) > 0:
                # Use most recent available day in history
                r.energy_yesterday = hist[sorted_dates[0]]
        else:
            # Fallback to energy_today or average
            r.energy_yesterday = getattr(r, "energy_today", 0.0) or (round(r.energy_this_month / 30.0, 2) if r.energy_this_month else 0.0)

        # 2. Resolve energy_weekly (actual sum of last 7 recorded days)
        if hist:
            sorted_dates = sorted(hist.keys(), reverse=True)
            last_7 = sorted_dates[:7]
            sum_7 = sum(hist[d] for d in last_7)
            r.energy_weekly = round(sum_7, 2)
        else:
            r.energy_weekly = round(r.energy_this_month / 4.33, 2) if r.energy_this_month else 0.0

