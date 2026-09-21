"""
Tests for Solaron CRM & Messaging Hub.
Verifies models, statement calculations, queue manager, and API routes.
"""

import pytest
from fastapi.testclient import TestClient
from app import app
from crm.db import init_crm_db, CRMSessionLocal
from crm.models import Customer, CampaignLog, MessageQueue
from crm.generator import get_monthly_statements, get_offline_plants
from crm.queue_manager import prepare_campaign, get_data_health, execute_campaign_dry_run
from crm.templates import render


@pytest.fixture(scope="module")
def client():
    init_crm_db()
    return TestClient(app)


def test_crm_data_health(client):
    res = client.get("/api/crm/health")
    assert res.status_code == 200
    data = res.json()
    assert "total_customers" in data
    assert "ready_to_message" in data
    assert "missing_phones" in data
    assert "unmapped_plants" in data


def test_crm_customer_crud(client):
    # 1. Create
    test_pid = "test-plant-999"
    create_res = client.post("/api/crm/customers", json={
        "plant_id": test_pid,
        "plant_name": "Test Solar Plant 999",
        "platform": "growatt",
        "customer_name": "Test Customer",
        "phone_number": "+919999999999",
        "opt_in_status": "active"
    })
    assert create_res.status_code == 200
    cust_id = create_res.json()["customer_id"]

    # 2. Read / List
    list_res = client.get(f"/api/crm/customers?search={test_pid}")
    assert list_res.status_code == 200
    customers = list_res.json()["customers"]
    assert any(c["plant_id"] == test_pid for c in customers)

    # 3. Update
    update_res = client.post(f"/api/crm/customers/{cust_id}", json={
        "customer_name": "Updated Customer Name",
        "opt_in_status": "do_not_send"
    })
    assert update_res.status_code == 200

    # Verify update in DB
    db = CRMSessionLocal()
    updated = db.query(Customer).filter(Customer.customer_id == cust_id).first()
    assert updated.customer_name == "Updated Customer Name"
    assert updated.opt_in_status == "do_not_send"

    # Cleanup test customer
    db.delete(updated)
    db.commit()
    db.close()


def test_monthly_statements_calculation():
    stmts = get_monthly_statements(2026, 9)
    assert len(stmts) > 0
    s = stmts[0]
    # Verify savings formula: gen_kwh * 14.0
    expected_savings = round(s.generation_kwh * 14.0, 2)
    assert s.savings_inr == expected_savings
    expected_co2 = round(s.generation_kwh * 0.82, 2)
    assert s.co2_saved_kg == expected_co2


def test_template_rendering():
    data = {
        "customer_name": "Ramesh",
        "plant_name": "Navi Mumbai-01",
        "generation_kwh": 420.5,
        "savings_inr": 5887.0,
        "co2_saved_kg": 344.8,
        "month_name": "September"
    }
    rendered = render("monthly_standard", data, lang="english")
    assert "Ramesh" in rendered
    assert "Navi Mumbai-01" in rendered
    assert "420.5 kWh" in rendered
    assert "₹5887" in rendered
    assert "344.8 kg" in rendered


def test_campaign_preparation_and_dry_run(client):
    res = client.post("/api/crm/campaigns/prepare", json={"month": "2026-09"})
    assert res.status_code == 200
    camp_id = res.json()["campaign_id"]
    assert camp_id > 0

    # Dry-run
    dry_res = client.post(f"/api/crm/campaigns/{camp_id}/dry-run")
    assert dry_res.status_code == 200
    assert dry_res.json()["success"] is True

    # Details
    detail_res = client.get(f"/api/crm/campaigns/{camp_id}")
    assert detail_res.status_code == 200
    assert len(detail_res.json()["messages"]) > 0
