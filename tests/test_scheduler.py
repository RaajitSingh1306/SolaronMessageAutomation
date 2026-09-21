from unittest.mock import patch
from services.excel import PlantRecord
from services.scheduler import hydrate_state_from_cache, SolaronScheduler
from state import get_state, update_state

def test_hydrate_state_from_cache():
    update_state(classified={}, response_data=None)

    fake_records = [
        PlantRecord("Plant Alpha", 100.0, 500.0, 1000.0, 0, 0, 0, 0, 0, "", "", 1, source="growatt", current_power_kw=5.0, energy_today=15.0),
        PlantRecord("Plant Beta", 0.0, 0.0, 200.0, 0, 0, 0, 0, 0, "", "", 2, source="isolarcloud"),
    ]

    with patch("services.scheduler.get_growatt_cache", return_value=(fake_records, {})):
        with patch("services.scheduler.get_isolar_cache", return_value=None):
            with patch("services.scheduler.get_suryalog_cache", return_value=None):
                result = hydrate_state_from_cache("2026-08")
                assert result is True
                state = get_state()
                assert "Active" in state.classified
                assert len(state.classified["Active"]) == 1
                assert state.classified["Active"][0].plant_name == "Plant Alpha"
                assert "Offline" in state.classified
                assert len(state.classified["Offline"]) == 1
                assert state.classified["Offline"][0].plant_name == "Plant Beta"


def test_scheduler_lifecycle():
    scheduler = SolaronScheduler()
    # Test safe start and stop
    scheduler.start()
    assert scheduler._thread is not None
    scheduler.stop()
    assert scheduler._stop_event.is_set()
