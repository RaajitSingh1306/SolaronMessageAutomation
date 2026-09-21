import os
import pytest
from services.excel import PlantRecord
from services.isolarcloud import (
    ISolarCloudFetcher,
    clear_cache,
    get_cached_data,
    is_cache_fresh,
    save_to_cache,
)

def test_isolarcloud_fetcher_init():
    fetcher = ISolarCloudFetcher(username="dummy_user", password="dummy_password")
    assert fetcher.username == "dummy_user"
    assert fetcher.password == "dummy_password"
    assert "isolarcloud" in fetcher.base_url


def test_isolarcloud_cache_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.ISOLARCLOUD_CACHE_DIR", str(tmp_path))

    # Freshness on non-existent cache
    assert not is_cache_fresh("2026-08")
    assert get_cached_data("2026-08") is None

    # Save records to cache
    sample = [
        PlantRecord(
            plant_name="Test Plant",
            energy_this_month=500.0,
            energy_this_year=0.0,
            energy_total=1000.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=0,
            source="isolarcloud",
            capacity_kwp=15.0,
            current_power_kw=5.0,
            energy_today=25.0,
            plant_status="normal",
            city="Pune",
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
    assert records[0].plant_name == "Test Plant"
    assert records[0].source == "isolarcloud"
    assert records[0].capacity_kwp == 15.0

    # Clear cache
    clear_cache("2026-08")
    assert not is_cache_fresh("2026-08")
    assert get_cached_data("2026-08") is None
