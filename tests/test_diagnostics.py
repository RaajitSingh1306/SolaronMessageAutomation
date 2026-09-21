from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_diagnostics_endpoint():
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "status" in data
    assert "portals" in data
    assert "growatt" in data["portals"]
    assert "isolarcloud" in data["portals"]
    assert "suryalog" in data["portals"]
    assert "contacts" in data
    assert "fleet" in data
    assert "automation" in data
