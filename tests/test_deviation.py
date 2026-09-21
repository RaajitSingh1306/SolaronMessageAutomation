import pytest
from services.excel import PlantRecord
from services.deviation import (
    calculate_specific_yield,
    calculate_fleet_benchmark,
    compute_deviations,
    detect_outliers_iqr,
)

def test_calculate_specific_yield():
    assert calculate_specific_yield(50.0, 10.0) == 5.0
    assert calculate_specific_yield(0.0, 10.0) == 0.0
    assert calculate_specific_yield(50.0, 0.0) == 0.0
    assert calculate_specific_yield(-5.0, 10.0) == 0.0

def test_fleet_benchmark_and_deviations():
    p1 = PlantRecord("Plant 1", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", 1, capacity_kwp=10.0, energy_today=40.0)  # yield = 4.0
    p2 = PlantRecord("Plant 2", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", 2, capacity_kwp=10.0, energy_today=40.0)  # yield = 4.0
    p3 = PlantRecord("Plant 3", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", 3, capacity_kwp=10.0, energy_today=20.0)  # yield = 2.0 (50% below 4.0)
    p4 = PlantRecord("Plant 4", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", 4, capacity_kwp=0.0, energy_today=10.0)   # no capacity

    records = [p1, p2, p3, p4]
    benchmark = calculate_fleet_benchmark(records, view_mode="daily")
    
    assert benchmark["benchmark_plants_count"] == 3
    # Mean yield: (4.0 + 4.0 + 2.0) / 3 = 3.333
    assert round(benchmark["fleet_mean_sy"], 2) == 3.33

    # Compute deviations against fleet
    res_records, stats = compute_deviations(records, view_mode="daily")
    assert len(res_records) == 4
    assert stats["benchmark_plants_count"] == 3
    # p1 yield is 4.0, benchmark mean ~3.333, so deviation should be positive
    assert p1.deviation_pct > 0
    # p3 yield is 2.0, benchmark mean ~3.333, so deviation should be negative
    assert p3.deviation_pct < 0

def test_detect_outliers_iqr():
    # Construct a list with an extreme underperformer
    recs = [
        PlantRecord(f"P{i}", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", i, capacity_kwp=10.0, energy_today=35.0 + i)
        for i in range(1, 15)
    ]
    # Add severe outlier
    outlier = PlantRecord("Outlier", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", 99, capacity_kwp=10.0, energy_today=1.0)
    recs.append(outlier)

    compute_deviations(recs, view_mode="daily")
    iqr_res = detect_outliers_iqr(recs)
    assert iqr_res["outliers_count"] >= 1
    assert iqr_res["lower_bound"] > 0
