import csv
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import Config
from services.contacts import get_phone_number
from services.excel import PlantRecord
from services.deviation import compute_deviations
from services.history import enrich_records_with_daily_history

logger = logging.getLogger(__name__)


def get_report_summary(
    records: List[PlantRecord],
    month_name: str = "",
    year: str = "",
    view_mode: str = "monthly",
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate summary KPIs across all records and platforms including deviation and status breakdown."""
    enrich_records_with_daily_history(records, target_date=target_date)
    records, dev_stats = compute_deviations(records, view_mode=view_mode, target_date=target_date)

    total_plants = len(records)
    total_energy_month = sum(r.energy_this_month for r in records)
    total_energy_today = sum(getattr(r, "energy_today", 0.0) for r in records)
    total_energy_yesterday = sum(getattr(r, "energy_yesterday", 0.0) for r in records)
    total_energy_weekly = sum(getattr(r, "energy_weekly", 0.0) for r in records)
    total_energy_year = sum(getattr(r, "energy_this_year", 0.0) for r in records)
    total_savings_month = round(total_energy_month * Config.PRICE_PER_UNIT, 2)
    total_savings_year = round(total_energy_year * Config.PRICE_PER_UNIT, 2)
    total_capacity_kwp = round(sum(getattr(r, "capacity_kwp", 0.0) for r in records), 2)

    by_source: Dict[str, Dict[str, Any]] = {}
    by_status: Dict[str, int] = {
        "Active": 0,
        "Not Working": 0,
        "Offline": 0,
        "Not Commissioned": 0,
    }

    for r in records:
        src = getattr(r, "source", "excel").lower()
        if src not in by_source:
            by_source[src] = {
                "count": 0,
                "energy_month": 0.0,
                "energy_today": 0.0,
                "energy_yesterday": 0.0,
                "energy_weekly": 0.0,
                "energy_year": 0.0,
                "capacity_kwp": 0.0,
                "active": 0,
                "not_working": 0,
                "offline": 0,
                "not_commissioned": 0,
            }
        by_source[src]["count"] += 1
        by_source[src]["energy_month"] += r.energy_this_month
        by_source[src]["energy_today"] += getattr(r, "energy_today", 0.0)
        by_source[src]["energy_yesterday"] += getattr(r, "energy_yesterday", 0.0)
        by_source[src]["energy_weekly"] += getattr(r, "energy_weekly", 0.0)
        by_source[src]["energy_year"] += getattr(r, "energy_this_year", 0.0)
        by_source[src]["capacity_kwp"] += getattr(r, "capacity_kwp", 0.0)

        # Status categorization
        e_month = r.energy_this_month or 0.0
        e_today = getattr(r, "energy_today", 0.0) or 0.0
        e_total = getattr(r, "energy_total", 0.0) or 0.0
        cur_power = getattr(r, "current_power_kw", 0.0) or 0.0
        dev_code = getattr(r, "device_status_code", 1)
        fault_code = getattr(r, "fault_code", "") or ""
        raw_status = (getattr(r, "plant_status", "") or "").strip().lower()

        if e_total <= 0 and e_month <= 0 and e_today <= 0:
            st = "Not Commissioned"
            by_status["Not Commissioned"] += 1
            by_source[src]["not_commissioned"] += 1
        elif fault_code != "" or dev_code == 2 or raw_status in ("fault", "abnormal", "not working", "error", "alarm") or (dev_code == 1 and e_today <= 0.0 and cur_power <= 0.0 and e_month > 0.0):
            st = "Not Working"
            by_status["Not Working"] += 1
            by_source[src]["not_working"] += 1
        elif dev_code == 0 or raw_status in ("offline", "lost", "disconnected") or (e_month <= 0.0 and e_today <= 0.0 and e_total > 0.0):
            st = "Offline"
            by_status["Offline"] += 1
            by_source[src]["offline"] += 1
        else:
            st = "Active"
            by_status["Active"] += 1
            by_source[src]["active"] += 1

    # Round figures in by_source
    for src, stats in by_source.items():
        stats["energy_month"] = round(stats["energy_month"], 2)
        stats["energy_today"] = round(stats["energy_today"], 2)
        stats["energy_yesterday"] = round(stats["energy_yesterday"], 2)
        stats["energy_weekly"] = round(stats["energy_weekly"], 2)
        stats["energy_year"] = round(stats["energy_year"], 2)
        stats["capacity_kwp"] = round(stats["capacity_kwp"], 2)
        stats["savings_month"] = round(stats["energy_month"] * Config.PRICE_PER_UNIT, 2)
        stats["savings_year"] = round(stats["energy_year"] * Config.PRICE_PER_UNIT, 2)

    return {
        "month_name": month_name,
        "year": year,
        "total_plants": total_plants,
        "total_energy_month_kwh": round(total_energy_month, 2),
        "total_energy_today_kwh": round(total_energy_today, 2),
        "total_energy_yesterday_kwh": round(total_energy_yesterday, 2),
        "total_energy_weekly_kwh": round(total_energy_weekly, 2),
        "total_energy_year_kwh": round(total_energy_year, 2),
        "total_savings_month_inr": total_savings_month,
        "total_savings_year_inr": total_savings_year,
        "total_capacity_kwp": total_capacity_kwp,
        "by_status": by_status,
        "by_source": by_source,
        "deviation_stats": dev_stats,
    }


def format_report_rows(
    records: List[PlantRecord],
    view_mode: str = "monthly",
    price_per_unit: float = 14.0,
    sort_by: str = "name",
    sort_order: str = "asc",
    year_label: str = "",
    target_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Format records according to daily, weekly, monthly, or yearly view mode with sorting and deviation metrics."""
    enrich_records_with_daily_history(records, target_date=target_date)
    records, dev_stats = compute_deviations(records, view_mode=view_mode, target_date=target_date)

    rows = []
    view = view_mode.lower()

    for r in records:
        src = getattr(r, "source", "growatt").lower()
        cap = getattr(r, "capacity_kwp", 0.0)
        cur_power = getattr(r, "current_power_kw", 0.0)
        e_today = getattr(r, "energy_today", 0.0)
        e_yesterday = getattr(r, "energy_yesterday", 0.0)
        e_weekly = getattr(r, "energy_weekly", 0.0)
        e_month = r.energy_this_month
        e_year = getattr(r, "energy_this_year", 0.0)
        e_total = r.energy_total

        # Compute relevant energy and savings for the selected view
        if view == "daily":
            if target_date and hasattr(r, "daily_history") and target_date in r.daily_history:
                energy = float(r.daily_history[target_date])
                period_label = target_date
            elif target_date == "yesterday" or (target_date and "yesterday" in target_date.lower()):
                energy = e_yesterday
                period_label = "Yesterday"
            else:
                energy = e_today
                period_label = target_date if target_date else "Today"
            savings = round(energy * price_per_unit, 2)
        elif view == "weekly":
            energy = e_weekly if e_weekly > 0 else (round(e_month / 4.33, 2) if e_month > 0 else 0.0)
            savings = round(energy * price_per_unit, 2)
            period_label = "Past 7 Days"
        elif view == "yearly":
            yr = str(year_label) if year_label else ""
            hist = getattr(r, "yearly_history", {}) or {}
            breakdown = getattr(r, "yearly_breakdown", {}) or {}
            if yr and yr in hist:
                energy = hist[yr]
            elif breakdown:
                energy = sum(float(v) for v in breakdown.values() if v)
            else:
                energy = e_year
            savings = round(energy * price_per_unit, 2)
            period_label = f"Year {yr}".strip() if yr else "This Year"
        else:  # monthly
            energy = e_month
            savings = round(e_month * price_per_unit, 2)
            period_label = "This Month"

        # Determine plant status (4-tier)
        dev_code = getattr(r, "device_status_code", 1)
        fault_code = getattr(r, "fault_code", "") or ""
        raw_status = (getattr(r, "plant_status", "") or "").strip().lower()

        if e_total <= 0 and e_month <= 0 and e_today <= 0:
            status = "Not Commissioned"
        elif fault_code != "" or dev_code == 2 or raw_status in ("fault", "abnormal", "not working", "error", "alarm") or (dev_code == 1 and e_today <= 0.0 and cur_power <= 0.0 and e_month > 0.0):
            status = "Not Working"
        elif dev_code == 0 or raw_status in ("offline", "lost", "disconnected") or (e_month <= 0.0 and e_today <= 0.0 and e_total > 0.0):
            status = "Offline"
        else:
            status = "Active"

        phone = get_phone_number(r.plant_name)

        rows.append({
            "plant_name": r.plant_name,
            "source": src,
            "status": status,
            "capacity_kwp": round(cap, 2),
            "current_power_kw": round(cur_power, 2),
            "energy": round(energy, 2),
            "energy_period": period_label,
            "energy_today": round(e_today, 2),
            "energy_yesterday": round(e_yesterday, 2),
            "energy_weekly": round(e_weekly, 2),
            "energy_month": round(e_month, 2),
            "energy_year": round(e_year, 2),
            "energy_total": round(e_total, 2),
            "specific_yield": getattr(r, "specific_yield", 0.0),
            "deviation_pct": getattr(r, "deviation_pct", 0.0),
            "z_score": getattr(r, "z_score", 0.0),
            "is_deviated": bool(getattr(r, "deviation_pct", 0.0) <= -15.0),
            "daily_history": getattr(r, "daily_history", {}),
            "yearly_breakdown": getattr(r, "yearly_breakdown", {}),
            "yearly_history": getattr(r, "yearly_history", {}),
            "savings": savings,
            "phone": phone,
            "message_status": r.message_status or "",
            "city": getattr(r, "city", "") or "",
        })

    # Apply sorting: name, capacity, energy, saving/savings, yield, deviation
    sort_key = (sort_by or "name").lower().strip()
    reverse = (sort_order or "asc").lower().strip() == "desc"
    if sort_key == "capacity":
        rows.sort(key=lambda x: (x.get("capacity_kwp") or 0.0), reverse=reverse)
    elif sort_key == "energy":
        rows.sort(key=lambda x: (x.get("energy") or 0.0), reverse=reverse)
    elif sort_key in ("saving", "savings"):
        rows.sort(key=lambda x: (x.get("savings") or 0.0), reverse=reverse)
    elif sort_key in ("yield", "specific_yield"):
        rows.sort(key=lambda x: (x.get("specific_yield") or 0.0), reverse=reverse)
    elif sort_key in ("deviation", "deviation_pct"):
        rows.sort(key=lambda x: (x.get("deviation_pct") or 0.0), reverse=reverse)
    else:
        rows.sort(key=lambda x: (x.get("plant_name") or "").lower(), reverse=reverse)

    return rows

    return rows


def export_report_to_csv(
    records: List[PlantRecord],
    view_mode: str = "monthly",
    month_name: str = "",
    year: str = "",
    sort_by: str = "name",
    sort_order: str = "asc",
) -> str:
    """
    Export records to a CSV file.
    Returns the absolute path to the generated CSV file.
    """
    rows = format_report_rows(
        records,
        view_mode=view_mode,
        price_per_unit=Config.PRICE_PER_UNIT,
        sort_by=sort_by,
        sort_order=sort_order,
        year_label=year,
    )
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_view = view_mode.lower()
    filename = f"solaron_{safe_view}_report_{month_name}_{year}_{timestamp}.csv".replace(" ", "_")
    output_path = os.path.join(Config.UPLOAD_FOLDER, filename)

    energy_col_title = f"Energy ({rows[0]['energy_period']} kWh)" if rows else "Energy (kWh)"

    fieldnames = [
        "Plant Name",
        "Source",
        "Status",
        "Capacity (kWp)",
        "Current Power (kW)",
        energy_col_title,
        "Month Energy (kWh)",
        "Year Energy (kWh)",
        "Total Energy (kWh)",
        "Savings (INR)",
        "Phone Number",
        "Message Sent Status",
        "City",
    ]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for r in rows:
            writer.writerow([
                r["plant_name"],
                r["source"].capitalize(),
                r["status"],
                r["capacity_kwp"],
                r["current_power_kw"],
                r["energy"],
                r.get("energy_month", 0.0),
                r.get("energy_year", 0.0),
                r["energy_total"],
                r["savings"],
                r["phone"],
                r["message_status"],
                r["city"],
            ])

    logger.info("Exported %d rows to CSV at: %s", len(rows), output_path)
    return output_path
