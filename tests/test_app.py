import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app import app
from state import get_state, update_state

client = TestClient(app)

def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

@patch("routes.send.send_whatsapp_messages")
def test_test_send_endpoint(mock_send, monkeypatch):
    monkeypatch.setenv("TEST_PHONE_NUMBER", "+919999999999")
    monkeypatch.setattr("config.Config.TEST_PHONE_NUMBER", "+919999999999")
    mock_send.return_value = {"sent": 1, "failed": 0, "total": 1, "errors": []}
    
    monkeypatch.setenv("API_KEY", "test-key")
    response = client.post("/api/test-send", headers={"X-API-Key": "test-key"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["results"]["sent"] == 1
    
    mock_send.assert_called_once()

def test_get_plants_status_empty(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from app import app
    update_state(classified={})
    
    with patch("routes.plants.hydrate_state_from_cache", return_value=False):
        response = client.get("/api/plants", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == {}


@patch("routes.fetch.GrowattFetcher")
def test_process_upload_endpoint(mock_fetcher_cls):
    response = client.post("/upload")
    assert response.status_code == 422 # Missing file


def test_send_queue_controls(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    headers = {"X-API-Key": "test-key"}
    
    from state import _add_job, get_send_job
    _add_job("test-job-ctrl", {"status": "running", "total": 5, "current": 1})
    
    # 1. Pause
    res = client.post("/api/send/pause", headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert get_send_job("test-job-ctrl")["status"] == "paused"
    
    # 2. Skip
    res = client.post("/api/send/skip", headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert get_send_job("test-job-ctrl")["skip_requested"] is True
    
    # 3. Next / Advance
    res = client.post("/api/send/next", headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert get_send_job("test-job-ctrl")["advance_requested"] is True
    
    # 4. Resume
    res = client.post("/api/send/resume", headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert get_send_job("test-job-ctrl")["status"] == "running"
    
    # 5. Cancel
    res = client.post("/api/send/cancel", headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert get_send_job("test-job-ctrl")["status"] == "cancelled"

