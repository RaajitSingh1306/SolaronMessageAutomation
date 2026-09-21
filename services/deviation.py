"""
services/deviation.py

Solar Fleet Deviation Detection and Performance Benchmarking Engine.
Adapted from Dashboard2 analytics formulas:
- Specific Yield (SY): kWh/kWp
- Fleet Benchmark: Mean and standard deviation of SY across active plants
- Deviation %: ((Plant SY - Fleet Mean SY) / Fleet Mean SY) * 100
- Fleet Z-Score: (Plant SY - Fleet Mean SY) / Fleet Std SY
- Underperformance Alert: Flag plants with deviation <= threshold (e.g. -15% or -25%)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from services.excel import PlantRecord

logger = logging.getLogger(__name__)


def calculate_specific_yield(energy_kwh: float, capacity_kwp: float) -> float:
    """Calculate specific yield in kWh/kWp, rounded to 3 decimal places."""
    if capacity_kwp and capacity_kwp > 0 and energy_kwh and energy_kwh > 0:
        return round(float(energy_kwh) / float(capacity_kwp), 3)
    return 0.0


def calculate_fleet_benchmark(
    records: List[PlantRecord],
    view_mode: str = "monthly",
    target_date: Optional[str] = None,
) -> Dict[str, float]:
    """
    Compute fleet-wide mean and standard deviation of specific yield
    for active/generating plants in the current view.
    """
    yields: List[float] = []
    total_capacity = 0.0
    total_energy = 0.0

    for r in records:
        cap = getattr(r, "capacity_kwp", 0.0) or 0.0
        if cap <= 0:
            continue
        total_capacity += cap

        # Determine energy for the active view
        energy = 0.0
        if view_mode == "daily":
            if target_date and hasattr(r, "daily_history") and target_date in r.daily_history:
                energy = float(r.daily_history[target_date])
            elif getattr(r, "energy_yesterday", 0.0) > 0 and target_date == "yesterday":
                energy = float(r.energy_yesterday)
            else:
                energy = float(getattr(r, "energy_today", 0.0) or 0.0)
        elif view_mode == "weekly":
            if getattr(r, "energy_weekly", 0.0) > 0:
                energy = float(r.energy_weekly)
            else:
                energy = float(r.energy_this_month / 4.33) if r.energy_this_month else 0.0
        elif view_mode == "yearly":
            energy = float(getattr(r, "energy_this_year", 0.0) or 0.0)
        else:  # monthly
            energy = float(r.energy_this_month or 0.0)

        total_energy += energy

        # Only include actively generating plants in the benchmark mean
        if energy > 0:
            sy = calculate_specific_yield(energy, cap)
            if sy > 0.05:  # filter out micro-trickle anomalies
                yields.append(sy)

    if not yields:
        # Fallback aggregate if individual yields empty
        overall_sy = (total_energy / total_capacity) if total_capacity > 0 else 0.0
        return {
            "fleet_mean_sy": round(overall_sy, 3),
            "fleet_std_sy": 0.0,
            "benchmark_plants_count": 0,
            "total_capacity_kwp": round(total_capacity, 2),
        }

    n = len(yields)
    mean_sy = sum(yields) / n
    variance = sum((x - mean_sy) ** 2 for x in yields) / n if n > 1 else 0.0
    std_sy = variance ** 0.5

    return {
        "fleet_mean_sy": round(mean_sy, 3),
        "fleet_std_sy": round(std_sy, 3),
        "benchmark_plants_count": n,
        "total_capacity_kwp": round(total_capacity, 2),
    }


def compute_deviations(
    records: List[PlantRecord],
    view_mode: str = "monthly",
    target_date: Optional[str] = None,
    threshold_pct: float = -15.0,
) -> Tuple[List[PlantRecord], Dict[str, Any]]:
    """
    Annotate each PlantRecord in place with:
    - specific_yield: float (kWh/kWp)
    - deviation_pct: float (% above or below fleet mean)
    - z_score: float (normalized statistical distance)

    Returns:
        records: annotated list of PlantRecord
        stats: dictionary of fleet deviation summary KPIs
    """
    benchmark = calculate_fleet_benchmark(records, view_mode=view_mode, target_date=target_date)
    mean_sy = benchmark["fleet_mean_sy"]
    std_sy = benchmark["fleet_std_sy"]

    deviated_count = 0
    severe_deviated_count = 0

    for r in records:
        cap = getattr(r, "capacity_kwp", 0.0) or 0.0
        energy = 0.0
        if view_mode == "daily":
            if target_date and hasattr(r, "daily_history") and target_date in r.daily_history:
                energy = float(r.daily_history[target_date])
            elif getattr(r, "energy_yesterday", 0.0) > 0 and target_date == "yesterday":
                energy = float(r.energy_yesterday)
            else:
                energy = float(getattr(r, "energy_today", 0.0) or 0.0)
        elif view_mode == "weekly":
            if getattr(r, "energy_weekly", 0.0) > 0:
                energy = float(r.energy_weekly)
            else:
                energy = float(r.energy_this_month / 4.33) if r.energy_this_month else 0.0
        elif view_mode == "yearly":
            energy = float(getattr(r, "energy_this_year", 0.0) or 0.0)
        else:
            energy = float(r.energy_this_month or 0.0)

        sy = calculate_specific_yield(energy, cap)
        r.specific_yield = sy

        # Calculate deviation %
        if mean_sy > 0.01 and cap > 0:
            dev_pct = ((sy - mean_sy) / mean_sy) * 100.0
            r.deviation_pct = round(dev_pct, 1)

            if std_sy > 0.001:
                r.z_score = round((sy - mean_sy) / std_sy, 2)
            else:
                r.z_score = 0.0
        else:
            r.deviation_pct = 0.0
            r.z_score = 0.0

        # Count underperformers
        if cap > 0 and mean_sy > 0.1:
            if r.deviation_pct <= threshold_pct:
                deviated_count += 1
            if r.deviation_pct <= -25.0:
                severe_deviated_count += 1

    stats = {
        **benchmark,
        "threshold_pct": threshold_pct,
        "deviated_count": deviated_count,
        "severe_deviated_count": severe_deviated_count,
    }

    return records, stats


def detect_outliers_iqr(records: List[PlantRecord]) -> Dict[str, Any]:
    """Detect statistical outliers using Interquartile Range (IQR) on Specific Yield."""
    valid_sys = sorted([r.specific_yield for r in records if getattr(r, "specific_yield", 0.0) > 0])
    if len(valid_sys) < 4:
        return {"outliers_count": 0, "lower_bound": 0.0, "upper_bound": 0.0}

    n = len(valid_sys)
    q25 = valid_sys[int(n * 0.25)]
    q75 = valid_sys[int(n * 0.75)]
    iqr = q75 - q25
    lower_bound = round(max(0.0, q25 - 1.5 * iqr), 3)
    upper_bound = round(q75 + 1.5 * iqr, 3)

    outliers = [r for r in records if (r.specific_yield < lower_bound or r.specific_yield > upper_bound) and r.specific_yield > 0]

    return {
        "outliers_count": len(outliers),
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "q25": round(q25, 3),
        "q75": round(q75, 3),
    }
