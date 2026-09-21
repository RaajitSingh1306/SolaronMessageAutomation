import os
import pytest
from services.excel import PlantRecord
from services.suryalog import (
    SuryaLogFetcher,
    clear_cache,
    get_cached_data,
    is_cache_fresh,
    save_to_cache,
)

def test_suryalog_fetcher_init():
    fetcher = SuryaLogFetcher(username="dummy_user", password="dummy_password")
    assert fetcher.username == "dummy_user"
    assert fetcher.password == "dummy_password"
    assert "suryalog" in fetcher.base_url


def test_suryalog_cache_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.SURYALOG_CACHE_DIR", str(tmp_path))

    # Freshness on non-existent cache
    assert not is_cache_fresh("2026-08")
    assert get_cached_data("2026-08") is None

    # Save records to cache
    sample = [
        PlantRecord(
            plant_name="Surya Plant 1",
            energy_this_month=720.0,
            energy_this_year=0.0,
            energy_total=2400.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=150.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=0,
            source="suryalog",
            capacity_kwp=20.0,
            current_power_kw=8.0,
            energy_today=35.0,
            plant_status="normal",
            city="Nagpur",
        )
    ]
    save_to_cache("2026-08", sample)

    # Freshness after save
    assert is_cache_fresh("2026-08")

    # Read from cache
    cached = get_cached_data("2026-08")
    assert cached is not None
    records, meta = cached
    assert len(records) == 1
    assert records[0].plant_name == "Surya Plant 1"
    assert records[0].source == "suryalog"
    assert records[0].co2_this_month == 150.0

    # Clear cache
    clear_cache("2026-08")
    assert not is_cache_fresh("2026-08")
    assert get_cached_data("2026-08") is None
