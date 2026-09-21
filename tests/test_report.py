import os
import pytest
from fastapi.testclient import TestClient
from app import app
from services.excel import PlantRecord
from services.report import export_report_to_csv, format_report_rows, get_report_summary
from state import update_state

client = TestClient(app)

@pytest.fixture
def sample_records():
    return [
        PlantRecord(
            plant_name="Plant Alpha",
            energy_this_month=1200.0,
            energy_this_year=5000.0,
            energy_total=15000.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=7,
            source="growatt",
            capacity_kwp=10.0,
            current_power_kw=4.5,
            energy_today=45.0,
            plant_status="normal",
            city="Nagpur",
        ),
        PlantRecord(
            plant_name="Plant Beta",
            energy_this_month=0.0,
            energy_this_year=1200.0,
            energy_total=8000.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=8,
            source="isolarcloud",
            capacity_kwp=5.0,
            current_power_kw=0.0,
            energy_today=0.0,
            plant_status="offline",
            city="Pune",
        ),
        PlantRecord(
            plant_name="Plant Gamma",
            energy_this_month=850.0,
            energy_this_year=2000.0,
            energy_total=3000.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=9,
            source="suryalog",
            capacity_kwp=8.0,
            current_power_kw=3.2,
            energy_today=30.0,
            plant_status="normal",
            city="Mumbai",
        ),
    ]


def test_get_report_summary(sample_records):
    summary = get_report_summary(sample_records, month_name="August", year="2026")
    assert summary["total_plants"] == 3
    assert summary["total_energy_month_kwh"] == 2050.0
    assert summary["total_energy_today_kwh"] == 75.0
    assert summary["total_capacity_kwp"] == 23.0
    assert summary["by_status"]["Active"] == 2
    assert summary["by_status"]["Offline"] == 1
    assert "growatt" in summary["by_source"]
    assert "isolarcloud" in summary["by_source"]
    assert "suryalog" in summary["by_source"]


def test_format_report_rows(sample_records):
    monthly_rows = format_report_rows(sample_records, view_mode="monthly")
    assert len(monthly_rows) == 3
    assert monthly_rows[0]["energy"] == 1200.0
    assert monthly_rows[0]["savings"] == 1200.0 * 14.0

    daily_rows = format_report_rows(sample_records, view_mode="daily")
    assert len(daily_rows) == 3
    assert daily_rows[0]["energy"] == 45.0
    assert daily_rows[0]["savings"] == 45.0 * 14.0

    weekly_rows = format_report_rows(sample_records, view_mode="weekly")
    assert len(weekly_rows) == 3
    assert weekly_rows[0]["energy"] == round(1200.0 / 4.33, 2)


def test_export_report_to_csv(sample_records, tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.UPLOAD_FOLDER", str(tmp_path))
    csv_file = export_report_to_csv(sample_records, view_mode="monthly", month_name="August", year="2026")
    assert os.path.exists(csv_file)
    with open(csv_file, "r", encoding="utf-8-sig") as f:
        content = f.read()
    assert "Plant Alpha" in content
    assert "Plant Beta" in content
    assert "Plant Gamma" in content
    assert "Growatt" in content
    assert "Isolarcloud" in content
    assert "Suryalog" in content


def test_report_api_endpoints(sample_records):
    # Setup state
    classified = {
        "Active": [sample_records[0], sample_records[2]],
        "Offline": [sample_records[1]],
        "Not Commissioned": [],
    }
    update_state(
        classified=classified,
        month_name="August",
        year="2026",
        response_data=None,
    )

    # 1. /api/report
    res = client.get("/api/report?view=monthly")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["total_rows"] == 3

    # Filter by source
    res_gw = client.get("/api/report?view=monthly&source=growatt")
    assert res_gw.status_code == 200
    assert res_gw.json()["total_rows"] == 1
    assert res_gw.json()["rows"][0]["plant_name"] == "Plant Alpha"

    # 2. /api/report/summary
    res_sum = client.get("/api/report/summary")
    assert res_sum.status_code == 200
    assert res_sum.json()["summary"]["total_plants"] == 3

    # 3. /api/report/csv
    res_csv = client.get("/api/report/csv?view=monthly")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert b"Plant Alpha" in res_csv.content

    # 4. API sort by capacity descending
    res_sort = client.get("/api/report?view=monthly&sort_by=capacity&sort_order=desc")
    assert res_sort.status_code == 200
    rows = res_sort.json()["rows"]
    assert [r["plant_name"] for r in rows] == ["Plant Alpha", "Plant Gamma", "Plant Beta"]


def test_format_report_rows_sorting(sample_records):
    # Sort by capacity descending (Alpha: 10, Gamma: 8, Beta: 5)
    rows_cap_desc = format_report_rows(sample_records, sort_by="capacity", sort_order="desc")
    assert [r["plant_name"] for r in rows_cap_desc] == ["Plant Alpha", "Plant Gamma", "Plant Beta"]

    # Sort by capacity ascending
    rows_cap_asc = format_report_rows(sample_records, sort_by="capacity", sort_order="asc")
    assert [r["plant_name"] for r in rows_cap_asc] == ["Plant Beta", "Plant Gamma", "Plant Alpha"]

    # Sort by energy descending (Alpha: 1200, Gamma: 850, Beta: 0)
    rows_energy_desc = format_report_rows(sample_records, sort_by="energy", sort_order="desc")
    assert [r["plant_name"] for r in rows_energy_desc] == ["Plant Alpha", "Plant Gamma", "Plant Beta"]

    # Sort by name descending
    rows_name_desc = format_report_rows(sample_records, sort_by="name", sort_order="desc")
    assert [r["plant_name"] for r in rows_name_desc] == ["Plant Gamma", "Plant Beta", "Plant Alpha"]

    # Sort by savings descending
    rows_savings_desc = format_report_rows(sample_records, sort_by="savings", sort_order="desc")
    assert [r["plant_name"] for r in rows_savings_desc] == ["Plant Alpha", "Plant Gamma", "Plant Beta"]


def test_yearly_report_view(sample_records):
    # Test yearly formatted rows
    rows_yearly = format_report_rows(sample_records, view_mode="yearly", year_label="2026")
    assert len(rows_yearly) == 3
    # Plant Alpha energy_this_year is 5000.0
    alpha = next(r for r in rows_yearly if r["plant_name"] == "Plant Alpha")
    assert alpha["energy"] == 5000.0
    assert alpha["energy_period"] == "Year 2026"
    assert alpha["savings"] == round(5000.0 * 14.0, 2)

    # Test summary yearly KPIs
    summary = get_report_summary(sample_records, month_name="August", year="2026")
    assert summary["total_energy_year_kwh"] == 8200.0  # 5000 + 1200 + 2000
    assert summary["total_savings_year_inr"] == round(8200.0 * 14.0, 2)

