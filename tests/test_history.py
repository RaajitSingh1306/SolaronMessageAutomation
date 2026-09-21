import os
import pytest
from services.excel import PlantRecord
from services.history import (
    get_history_file_path,
    load_history,
    save_history,
    merge_yearly_plant_data,
    merge_batch_yearly_data,
    enrich_records_with_history,
)


def test_history_save_and_load(tmp_path, monkeypatch):
    test_hist_file = os.path.join(tmp_path, "yearly_data.json")
    monkeypatch.setattr("services.history.get_history_file_path", lambda: test_hist_file)

    data = {
        "fetched_at": "2026-09-02T10:00:00",
        "plants": {
            "growatt:Plant Test": {
                "plant_name": "Plant Test",
                "source": "growatt",
                "monthly_breakdown": {"2026": {"01": 120.0, "02": 150.0}},
                "yearly_totals": {"2026": 270.0, "2025": 1400.0, "2024": 1300.0},
            }
        }
    }
    assert save_history(data) is True

    loaded = load_history()
    assert "growatt:Plant Test" in loaded["plants"]
    assert loaded["plants"]["growatt:Plant Test"]["yearly_totals"]["2026"] == 270.0


def test_merge_yearly_plant_data(tmp_path, monkeypatch):
    test_hist_file = os.path.join(tmp_path, "yearly_data.json")
    monkeypatch.setattr("services.history.get_history_file_path", lambda: test_hist_file)

    # Merge current year with monthly breakdown
    hist = merge_yearly_plant_data(
        source="growatt",
        plant_name="Solar Home Alpha",
        year=2026,
        monthly_breakdown={"01": 100.0, "02": 150.0, "03": 200.0},
        yearly_total=450.0,
    )
    save_history(hist)

    # Merge older year total only
    hist = merge_yearly_plant_data(
        source="growatt",
        plant_name="Solar Home Alpha",
        year=2024,
        monthly_breakdown=None,
        yearly_total=1800.0,
        history_data=hist,
    )
    save_history(hist)

    loaded = load_history()
    plant = loaded["plants"]["growatt:Solar Home Alpha"]
    assert plant["monthly_breakdown"]["2026"]["01"] == 100.0
    assert plant["yearly_totals"]["2026"] == 450.0
    assert plant["yearly_totals"]["2024"] == 1800.0


def test_enrich_records_with_history(tmp_path, monkeypatch):
    test_hist_file = os.path.join(tmp_path, "yearly_data.json")
    monkeypatch.setattr("services.history.get_history_file_path", lambda: test_hist_file)

    data = {
        "plants": {
            "growatt:Plant Alpha": {
                "plant_name": "Plant Alpha",
                "source": "growatt",
                "monthly_breakdown": {"2026": {"01": 200.0, "02": 300.0}},
                "yearly_totals": {"2026": 500.0, "2025": 1200.0},
            }
        }
    }
    save_history(data)

    records = [
        PlantRecord(
            plant_name="Plant Alpha",
            energy_this_month=50.0,
            energy_this_year=0.0,
            energy_total=2000.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=7,
            source="growatt",
        )
    ]

    enrich_records_with_history(records, target_year=2026)
    assert records[0].energy_this_year == 500.0
    assert records[0].yearly_breakdown == {"01": 200.0, "02": 300.0}
    assert records[0].yearly_history == {"2026": 500.0, "2025": 1200.0}
