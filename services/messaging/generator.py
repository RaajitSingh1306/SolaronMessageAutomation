"""
services/message_generator.py

Generates WhatsApp message text for each plant status.
Templates are the exact messages used by the Solaron team.
"""

from config import Config
from services.excel import PlantRecord


from datetime import datetime

def generate_message(
    record: PlantRecord,
    status: str,
    month_name: str = "",
    year: str = "",
    view_mode: str = "monthly",
    date_str: str = "",
) -> str:
    """
    Generate the appropriate WhatsApp message for a plant.

    Args:
        record:     The PlantRecord to generate a message for.
        status:     "Active", "Offline", or "Not Commissioned".
        month_name: e.g. "July"  — extracted from filename.
        year:       e.g. "2026"  — extracted from filename.
        view_mode:  "daily", "weekly", "monthly", or "yearly".
        date_str:   Optional date string for daily report.

    Returns:
        Message string, or "" if no message should be sent (Not Commissioned).
    """
    if status == "Active":
        return _active_message(record, month_name, year, view_mode=view_mode, date_str=date_str)
    elif status == "Not Working":
        return _not_working_message()
    elif status == "Offline":
        return _offline_message()
    else:
        # Not Commissioned — no message sent
        return ""


def _active_message(
    record: PlantRecord,
    month_name: str,
    year: str,
    view_mode: str = "monthly",
    date_str: str = "",
) -> str:
    view = (view_mode or "monthly").lower()
    
    if view == "daily":
        if date_str and hasattr(record, "daily_history") and date_str in record.daily_history:
            energy_val = record.daily_history[date_str]
        elif date_str == "yesterday" or (date_str and "yesterday" in date_str.lower()):
            energy_val = getattr(record, "energy_yesterday", 0.0) or 0.0
        else:
            energy_val = getattr(record, "energy_today", 0.0) or 0.0
        energy = round(energy_val)
        savings = round(energy_val * Config.PRICE_PER_UNIT)
        d_str = date_str or datetime.now().strftime("%d %b %Y")
        return Config.MSG_DAILY.format(
            energy=energy,
            date=d_str,
            savings=savings,
        )
    elif view == "weekly":
        weekly_energy = getattr(record, "energy_weekly", 0.0)
        if not weekly_energy or weekly_energy <= 0:
            weekly_energy = (record.energy_this_month / 4.33) if record.energy_this_month else 0
        energy = round(weekly_energy)
        savings = round(weekly_energy * Config.PRICE_PER_UNIT)
        return Config.MSG_WEEKLY.format(
            energy=energy,
            savings=savings,
        )
    elif view == "yearly":
        yr = year or str(Config.year if hasattr(Config, "year") else datetime.now().year)
        hist = getattr(record, "yearly_history", {}) or {}
        y_energy = hist.get(str(yr)) or record.energy_this_year or 0
        energy = round(y_energy)
        savings = round(y_energy * Config.PRICE_PER_UNIT)
        return Config.MSG_YEARLY.format(
            energy=energy,
            year=yr,
            savings=savings,
        )
    else:
        # Default monthly
        energy = round(record.energy_this_month or 0)
        savings = round((record.energy_this_month or 0) * Config.PRICE_PER_UNIT)
        return Config.MSG_ACTIVE.format(
            energy=energy,
            month_name=month_name,
            year=year,
            savings=savings,
        )


def _offline_message() -> str:
    return Config.MSG_OFFLINE.format(
        support_phone=Config.SUPPORT_PHONE
    )


def _not_working_message() -> str:
    return Config.MSG_NOT_WORKING.format(
        support_phone=Config.SUPPORT_PHONE
    )


def generate_monsoon_message() -> str:
    """
    Seasonal monsoon pre-check message.
    Sent weekly during June and July to all contacts with phone numbers.
    """
    return Config.MSG_MONSOON
