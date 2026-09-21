import pytest
from unittest.mock import MagicMock, patch
from services.growatt import GrowattFetcher
from services.growatt.fetcher import _parse_energy_to_kwh

def test_parse_energy_to_kwh():
    assert _parse_energy_to_kwh(100) == 100.0
    assert _parse_energy_to_kwh(100.5) == 100.5
    assert _parse_energy_to_kwh("100.5 kWh") == 100.5
    assert _parse_energy_to_kwh("2.5 MWh") == 2500.0
    assert _parse_energy_to_kwh("1.5 GWh") == 1500000.0
    assert _parse_energy_to_kwh(None) == 0.0
    assert _parse_energy_to_kwh("") == 0.0
    assert _parse_energy_to_kwh("invalid") == 0.0

@patch("services.growatt.fetcher.growattServer.GrowattApi")
def test_growatt_login_success(mock_api_cls):
    mock_api = mock_api_cls.return_value
    mock_api.login.return_value = {"success": True, "user": {"id": 12345}}
    
    fetcher = GrowattFetcher("user", "pass", "url")
    assert fetcher.login() is True
    assert fetcher.user_id == 12345

@patch("services.growatt.fetcher.growattServer.GrowattApi")
def test_growatt_login_failure(mock_api_cls):
    mock_api = mock_api_cls.return_value
    mock_api.login.return_value = {"success": False, "msg": "Bad password"}
    
    fetcher = GrowattFetcher("user", "pass", "url")
    assert fetcher.login() is False
    assert fetcher.user_id is None

@patch("services.growatt.fetcher.growattServer.GrowattApi")
def test_fetch_all_plants(mock_api_cls):
    mock_api = mock_api_cls.return_value
    # Skip actual delay during tests
    with patch("services.growatt.fetcher.time.sleep"):
        fetcher = GrowattFetcher("user", "pass", "url")
        fetcher.user_id = 12345 # Pre-authenticate
        
        # Mock plant_list
        mock_api.plant_list.return_value = {
            "data": [
                {"plantId": 1, "plantName": "Plant A", "totalEnergy": "1.5 MWh"},
                {"plantId": 2, "plantName": "Plant B", "totalEnergy": "500 kWh"},
            ]
        }
        
        # Mock plant_detail
        # Plant A returns monthly energy directly
        # Plant B returns daily values that need summing
        def mock_plant_detail(plant_id, timespan, dt):
            if plant_id == 1:
                return {"data": {"currentMonthEnergy": "150 kWh"}}
            else:
                return {"plantData": {"data": {"1": "10", "2": "20.5", "3": ""}}}
        
        mock_api.plant_detail.side_effect = mock_plant_detail
        
        records, failed, time_taken = fetcher.fetch_all_plants("2026-08")
        
        assert len(failed) == 0
        assert len(records) == 2
        
        # Check Plant A
        assert records[0].plant_name == "Plant A"
        assert records[0].energy_this_month == 150.0
        assert records[0].energy_total == 1500.0 # 1.5 MWh
        
        # Check Plant B
        assert records[1].plant_name == "Plant B"
        assert records[1].energy_this_month == 30.5 # 10 + 20.5
        assert records[1].energy_total == 500.0


@patch("services.growatt.fetcher.growattServer.GrowattApi")
def test_fetch_real_growatt_api_structure(mock_api_cls):
    """Test actual structure returned by Growatt ShineServer API."""
    mock_api = mock_api_cls.return_value
    with patch("services.growatt.fetcher.time.sleep"):
        fetcher = GrowattFetcher("user", "pass", "url")
        fetcher.user_id = 12345
        
        mock_api.plant_list.return_value = {
            "data": [
                {
                    "plantId": 10795086,
                    "plantName": "Modispaces Amizarana Malad",
                    "todayEnergy": "54.6 kWh",
                    "totalEnergy": "5.7 MWh",
                }
            ]
        }
        
        # Real Growatt API structure
        mock_api.plant_detail.return_value = {
            "plantData": {
                "plantMoneyText": "16969.4 ",
                "plantId": "10795086",
                "currentEnergy": "1.21 MWh",
                "plantName": "Modispaces Amizarana Malad",
            },
            "data": {
                "01": "35.4", "02": "19.4", "03": "39.7", "04": "36.0",
                "28": "54.6",
            },
            "success": True,
        }
        
        records, failed, _ = fetcher.fetch_all_plants("2026-08")
        assert len(records) == 1
        r = records[0]
        assert r.plant_name == "Modispaces Amizarana Malad"
        # Must NOT equal single-day snapshot 54.6! Must be sum of days (185.1)
        assert r.energy_this_month == 185.1
        assert r.energy_today == 54.6
        assert r.savings == 16969.4
        assert r.energy_total == 5700.0

