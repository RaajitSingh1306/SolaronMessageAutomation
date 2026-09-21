"""
routes/diagnostics.py

Automated diagnostic and health-check API for Solaron Messaging Dashboard.
Checks credentials, browser engine, contact database integrity, portal caches, and fleet health.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter

from config import Config
from services.contacts import _load_cache, _phone_cache, get_phone_number
from services.growatt import get_cached_data as get_growatt_cache, is_cache_fresh as is_gw_fresh
from services.isolarcloud import get_cached_data as get_isolar_cache, is_cache_fresh as is_isc_fresh
from services.suryalog import get_cached_data as get_suryalog_cache, is_cache_fresh as is_sl_fresh
from state import get_state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/diagnostics")
def get_system_diagnostics() -> Dict[str, Any]:
    now = datetime.now()
    month_str = now.strftime("%Y-%m")
    state = get_state()

    issues: List[str] = []
    warnings: List[str] = []

    # 1. Credentials Check
    portals = {
        "growatt": {
            "configured": bool(Config.GROWATT_USER and Config.GROWATT_PASSWORD),
            "user": Config.GROWATT_USER,
            "cache_fresh_today": is_gw_fresh(month_str),
            "plant_count": 0,
        },
        "isolarcloud": {
            "configured": bool(Config.ISOLARCLOUD_USER and Config.ISOLARCLOUD_PASSWORD),
            "user": Config.ISOLARCLOUD_USER,
            "cache_fresh_today": is_isc_fresh(month_str),
            "plant_count": 0,
        },
        "suryalog": {
            "configured": bool(Config.SURYALOG_USER and Config.SURYALOG_PASSWORD),
            "user": Config.SURYALOG_USER,
            "cache_fresh_today": is_sl_fresh(month_str),
            "plant_count": 0,
        },
    }

    for p_name, p_data in portals.items():
        if not p_data["configured"]:
            issues.append(f"{p_name.capitalize()} credentials are missing in configuration.")

    # Read counts from caches
    gw_cache = get_growatt_cache(month_str)
    if gw_cache:
        portals["growatt"]["plant_count"] = len(gw_cache[0])

    isc_cache = get_isolar_cache(month_str)
    if isc_cache:
        portals["isolarcloud"]["plant_count"] = len(isc_cache[0])

    sl_cache = get_suryalog_cache(month_str)
    if sl_cache:
        portals["suryalog"]["plant_count"] = len(sl_cache[0])

    # 2. Contacts Health
    from services.contacts import get_cache_size
    total_contacts = get_cache_size()
    fleet_with_phone = 0
    fleet_without_phone = 0
    missing_samples: List[str] = []

    # Count for loaded fleet
    all_plants: List[str] = []
    if state.response_data and isinstance(state.response_data[0], dict):
        for plant_list in state.response_data[0].values():
            for p in plant_list:
                name = p.get("plant_name", "")
                all_plants.append(name)
                if p.get("phone"):
                    fleet_with_phone += 1
                else:
                    fleet_without_phone += 1
                    if len(missing_samples) < 5:
                        missing_samples.append(name)
    elif state.classified:
        for p_list in state.classified.values():
            for p in p_list:
                all_plants.append(p.plant_name)
                phone = get_phone_number(p.plant_name)
                if phone:
                    fleet_with_phone += 1
                else:
                    fleet_without_phone += 1
                    if len(missing_samples) < 5:
                        missing_samples.append(p.plant_name)


    if fleet_without_phone > 0:

        warnings.append(f"{fleet_without_phone} plants in current fleet do not have matching phone numbers.")

    # 3. Overall status calculation
    if issues:
        status = "error"
        status_msg = f"System has {len(issues)} critical issue(s)."
    elif warnings:
        status = "warning"
        status_msg = f"System operational with {len(warnings)} warning(s)."
    else:
        status = "healthy"
        status_msg = "All systems operational and synchronized."

    return {
        "success": True,
        "timestamp": now.isoformat(),
        "status": status,
        "status_message": status_msg,
        "issues": issues,
        "warnings": warnings,
        "portals": portals,
        "contacts": {
            "total_cached_contacts": total_contacts,
            "fleet_with_phone": fleet_with_phone,
            "fleet_without_phone": fleet_without_phone,
            "sample_missing_plants": missing_samples,
        },
        "fleet": {
            "total_plants": len(all_plants),
            "active": len(state.classified.get("Active", [])),
            "offline": len(state.classified.get("Offline", [])),
            "not_commissioned": len(state.classified.get("Not Commissioned", [])),
            "month_name": state.month_name,
            "year": state.year,
        },
        "automation": {
            "auto_load_on_startup": Config.AUTO_LOAD_ON_STARTUP,
            "auto_sync_enabled": Config.AUTO_SYNC_ENABLED,
            "daily_sync_hour": Config.AUTO_SYNC_DAILY_HOUR,
            "monthly_sync_day": Config.AUTO_SYNC_MONTHLY_DAY,
        },
    }
