import os
import tempfile
import json
from unittest.mock import patch

import services.contacts as contacts
from config import Config

def test_get_phone_number_cache_hit():
    contacts.clear_cache()
    # Manually populate cache and mark it loaded
    contacts._phone_cache["Plant Cache"] = "1111111111"
    contacts._cache_loaded = True
    
    phone = contacts.get_phone_number("Plant Cache")
    assert phone == "1111111111"

def test_get_phone_number_csv_lookup():
    contacts.clear_cache()
    from database import SessionLocal
    from models import PhoneCache
    db = SessionLocal()
    db.add(PhoneCache(plant_name="Gopal Naidu", phone_number="1111111111"))
    db.add(PhoneCache(plant_name="Vivek Mandir", phone_number="1234567890"))
    db.commit()
    db.close()
    
    phone = contacts.get_phone_number("Gopal Naidu")
    assert phone == "1111111111"
    
    # Case insensitive lookup
    phone2 = contacts.get_phone_number("vivek mandir")
    assert phone2 == "1234567890"
    
    # Partial match (CSV name is inside query name)
    phone3 = contacts.get_phone_number("Gopal Naidu - Res")
    assert phone3 == "1111111111"
    
    # Not found
    phone4 = contacts.get_phone_number("Unknown Plant")
    assert phone4 == ""

def test_save_and_load_cache():
    contacts.clear_cache()
    
    contacts._phone_cache["Test Plant"] = "2222222222"
    contacts.save_cache()
    
    # Clear in memory cache
    contacts.clear_cache()
    assert "Test Plant" not in contacts._phone_cache
    
    # get_phone_number triggers _load_cache
    phone = contacts.get_phone_number("Test Plant")
    assert phone == "2222222222"


def test_update_contact():
    contacts.clear_cache()
    res = contacts.update_contact("Solar Alpha", "9876543210")
    assert res["success"] is True
    assert res["phone"] == "9876543210"
    assert contacts.get_phone_number("Solar Alpha") == "9876543210"
    
    from database import SessionLocal
    from models import PhoneCache
    db = SessionLocal()
    record = db.query(PhoneCache).filter(PhoneCache.plant_name == "Solar Alpha").first()
    assert record is not None
    assert record.phone_number == "9876543210"
    db.close()

def test_import_contacts_from_csv():
    contacts.clear_cache()
    csv_text = (
        "Plant Name, Mobile Number\n"
        "Ramesh Solar, 9822334455\n"
        "Suresh Factory, 919876543210\n"
        "Invalid Plant, 12345\n"
    )
    res = contacts.import_contacts_from_csv(csv_text)
    assert res["success"] is True
    assert res["valid_imported"] == 2
    assert contacts.get_phone_number("Ramesh Solar") == "9822334455"
    assert contacts.get_phone_number("Suresh Factory") == "9876543210"


def test_contacts_api_endpoints():
    from fastapi.testclient import TestClient
    from app import app

    with TestClient(app) as client:
        # Test update
        resp = client.post("/api/contacts/update", json={"plant_name": "Test Rooftop", "phone": "9811223344"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["phone"] == "9811223344"
    
        # Test invalid phone
        resp2 = client.post("/api/contacts/update", json={"plant_name": "Test Rooftop", "phone": "123"})
        assert resp2.status_code == 400
    
        # Test CSV import
        csv_bytes = b"Name,Phone\nCustom Plant,9988776655\n"
        resp3 = client.post("/api/contacts/import-csv", files={"file": ("test.csv", csv_bytes, "text/csv")})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["success"] is True
        assert data3["valid_imported"] == 1

