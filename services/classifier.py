"""
services/classifier.py

Classifies PlantRecord objects into Active / Offline / Not Commissioned.

Classification is PURELY energy-based. The 'message status' column is NOT used
for classification — it may not exist in future files and is only written to
by excel_updater.py after messages are sent.
"""

from enum import Enum
from typing import Dict, List

from services.excel import PlantRecord


class PlantStatus(Enum):
    ACTIVE = "Active"
    NOT_WORKING = "Not Working"
    OFFLINE = "Offline"
    NOT_COMMISSIONED = "Not Commissioned"


def classify_plants(records: List[PlantRecord]) -> Dict[str, List[PlantRecord]]:
    """
    Classify a list of PlantRecord objects by energy and hardware operational state.

    Rules (priority order):
        1. energy_total == 0
           → Not Commissioned (brand new site, never produced power)
        2. Fault / Abnormal / Inverter Tripped:
           - Explicit fault code, or device_status_code == 2, or plant_status == 'fault'/'abnormal',
           - OR online communication but 0 power and 0 generation today while previously active this month
           → Not Working
        3. Communication lost / Datalogger offline:
           - device_status_code == 0 or plant_status == 'offline',
           - OR energy_this_month == 0 AND energy_today == 0 AND energy_total > 0
           → Offline
        4. Power generation:
           - energy_this_month > 0 OR energy_today > 0 OR current_power_kw > 0
           → Active

    Returns:
        Dict with keys "Active", "Not Working", "Offline", "Not Commissioned",
        each mapping to a list of PlantRecord.
    """
    classified: Dict[str, List[PlantRecord]] = {
        PlantStatus.ACTIVE.value: [],
        PlantStatus.NOT_WORKING.value: [],
        PlantStatus.OFFLINE.value: [],
        PlantStatus.NOT_COMMISSIONED.value: [],
    }

    for record in records:
        e_month = getattr(record, "energy_this_month", 0.0) or 0.0
        e_today = getattr(record, "energy_today", 0.0) or 0.0
        e_total = getattr(record, "energy_total", 0.0) or 0.0
        cur_power = getattr(record, "current_power_kw", 0.0) or 0.0
        dev_code = getattr(record, "device_status_code", 1)
        fault_code = getattr(record, "fault_code", "") or ""
        raw_status = (getattr(record, "plant_status", "") or "").strip().lower()

        # 1. Not Commissioned: Never generated any power
        if e_total <= 0 and e_month <= 0 and e_today <= 0:
            classified[PlantStatus.NOT_COMMISSIONED.value].append(record)
            continue

        # 2. Not Working (Inverter fault / tripped / zero generation while online)
        is_fault = (
            fault_code != ""
            or dev_code == 2
            or raw_status in ("fault", "abnormal", "not working", "error", "alarm")
        )
        is_zero_gen_while_online = (
            dev_code == 1
            and e_today <= 0.0
            and cur_power <= 0.0
            and e_month > 0.0
        )
        if is_fault or is_zero_gen_while_online:
            classified[PlantStatus.NOT_WORKING.value].append(record)
            continue

        # 3. Offline (Datalogger lost communication / unreachable)
        is_offline = (
            dev_code == 0
            or raw_status in ("offline", "lost", "disconnected")
            or (e_month <= 0.0 and e_today <= 0.0 and e_total > 0.0)
        )
        if is_offline:
            classified[PlantStatus.OFFLINE.value].append(record)
            continue

        # 4. Active (Normal power generation)
        classified[PlantStatus.ACTIVE.value].append(record)

    return classified


