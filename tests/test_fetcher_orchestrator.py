from unittest.mock import MagicMock, patch
import pytest
from services.excel import PlantRecord
from services.fetcher_orchestrator import fetch_from_sources

@pytest.fixture
def mock_gw_records():
    return [
        PlantRecord(
            plant_name="GW-1",
            energy_this_month=100.0,
            energy_this_year=0.0,
            energy_total=500.0,
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

@pytest.fixture
def mock_isc_records():
    return [
        PlantRecord(
            plant_name="ISC-1",
            energy_this_month=200.0,
            energy_this_year=0.0,
            energy_total=800.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=0,
            source="isolarcloud",
        )
    ]

@pytest.fixture
def mock_sl_records():
    return [
        PlantRecord(
            plant_name="SL-1",
            energy_this_month=300.0,
            energy_this_year=0.0,
            energy_total=1200.0,
            income_this_month=0.0,
            income_total=0.0,
            co2_this_month=0.0,
            co2_total=0.0,
            savings=0.0,
            message_status="",
            nut_bolts="",
            row_index=0,
            source="suryalog",
        )
    ]


@patch("services.fetcher_orchestrator.get_growatt_cache")
@patch("services.fetcher_orchestrator.get_isolar_cache")
@patch("services.fetcher_orchestrator.get_suryalog_cache")
def test_fetch_from_sources_from_cache(
    mock_sl_cache,
    mock_isc_cache,
    mock_gw_cache,
    mock_gw_records,
    mock_isc_records,
    mock_sl_records,
):
    mock_gw_cache.return_value = (mock_gw_records, {"count": 1})
    mock_isc_cache.return_value = (mock_isc_records, {"count": 1})
    mock_sl_cache.return_value = (mock_sl_records, {"count": 1})

    records, failed, elapsed = fetch_from_sources("2026-08")

    assert len(records) == 3
    assert {r.source for r in records} == {"growatt", "isolarcloud", "suryalog"}
    assert len(failed) == 0


@patch("services.fetcher_orchestrator.get_growatt_cache")
@patch("services.fetcher_orchestrator.get_isolar_cache")
@patch("services.fetcher_orchestrator.get_suryalog_cache")
@patch("services.fetcher_orchestrator.ISolarCloudFetcher")
def test_fetch_from_sources_error_isolation(
    mock_isc_fetcher_cls,
    mock_sl_cache,
    mock_isc_cache,
    mock_gw_cache,
    mock_gw_records,
):
    # Growatt succeeds from cache
    mock_gw_cache.return_value = (mock_gw_records, {"count": 1})
    # iSolarCloud cache miss and fetcher fails with exception
    mock_isc_cache.return_value = None
    mock_instance = MagicMock()
    mock_instance.fetch_all_plants.side_effect = RuntimeError("Playwright connection timeout")
    mock_isc_fetcher_cls.return_value = mock_instance
    # SuryaLog returns empty
    mock_sl_cache.return_value = None

    records, failed, elapsed = fetch_from_sources("2026-08", sources=["growatt", "isolarcloud"])

    # Growatt records should still be present despite iSolarCloud failing!
    assert len(records) == 1
    assert records[0].source == "growatt"
    assert len(failed) == 1
    assert failed[0]["source"] == "isolarcloud"
    assert "Playwright connection timeout" in failed[0]["error"]


@patch("services.fetcher_orchestrator.get_growatt_cache")
@patch("services.fetcher_orchestrator.get_isolar_cache")
@patch("services.fetcher_orchestrator.get_suryalog_cache")
@patch("services.fetcher_orchestrator.GrowattFetcher")
def test_fetch_from_sources_deselected_growatt(
    mock_gw_fetcher_cls,
    mock_sl_cache,
    mock_isc_cache,
    mock_gw_cache,
    mock_isc_records,
    mock_sl_records,
):
    """When Growatt is not in sources, Growatt fetcher and cache must NOT be touched."""
    mock_isc_cache.return_value = (mock_isc_records, {"count": 1})
    mock_sl_cache.return_value = (mock_sl_records, {"count": 1})

    records, failed, elapsed = fetch_from_sources("2026-08", sources=["isolarcloud", "suryalog"])

    assert len(records) == 2
    assert {r.source for r in records} == {"isolarcloud", "suryalog"}
    # Growatt was not requested, so it must not be called
    mock_gw_cache.assert_not_called()
    mock_gw_fetcher_cls.assert_not_called()


@patch("services.fetcher_orchestrator.get_growatt_cache")
@patch("services.fetcher_orchestrator.get_isolar_cache")
def test_fetch_from_sources_cancellation(
    mock_isc_cache,
    mock_gw_cache,
    mock_gw_records,
    mock_isc_records,
):
    """When cancel_check returns True, fetching should abort immediately."""
    mock_gw_cache.return_value = (mock_gw_records, {"count": 1})
    mock_isc_cache.return_value = (mock_isc_records, {"count": 1})

    # Abort before second source
    calls = 0
    def cancel_after_first():
        nonlocal calls
        calls += 1
        return calls > 1

    records, failed, elapsed = fetch_from_sources(
        "2026-08",
        sources=["growatt", "isolarcloud"],
        cancel_check=cancel_after_first
    )

    assert len(records) == 1
    assert records[0].source == "growatt"
    mock_isc_cache.assert_not_called()
