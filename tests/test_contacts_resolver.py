import tempfile
import os
from unittest.mock import patch
import services.contacts as contacts
from config import Config

def test_empty_token_subset_regression():
    """Verify that a non-alphabetic entry (like a raw phone number or punctuation)
    does not match all 2-word plant names due to empty set subset behavior."""
    contacts.clear_cache()

    from database import SessionLocal
    from models import PhoneCache
    db = SessionLocal()
    db.add(PhoneCache(plant_name="'+917030605273'", phone_number="7030605273"))
    db.add(PhoneCache(plant_name="...", phone_number="9999999999"))
    db.add(PhoneCache(plant_name="John Doe", phone_number="9876543210"))
    db.commit()
    db.close()

    # 'Shailendra Dhomne' has 2 words and does NOT match John Doe or the raw phone entry
    phone = contacts.get_phone_number("Shailendra Dhomne")
    assert phone != "7030605273"
    assert phone == ""

    # John Doe should match
    phone_john = contacts.get_phone_number("John Doe")
    assert phone_john == "9876543210"


def test_clean_phone_number_validation():
    """Test 10-digit Indian phone sanitization."""
    from services.contacts import _clean_phone_number

    assert _clean_phone_number("+919876543210") == "9876543210"
    assert _clean_phone_number("919876543210") == "9876543210"
    assert _clean_phone_number("09876543210") == "9876543210"
    assert _clean_phone_number("9876543210") == "9876543210"
    assert _clean_phone_number(" 98765 43210 ") == "9876543210"
    # Too short or garbage
    assert _clean_phone_number("12345") == ""
    assert _clean_phone_number("invalid") == ""


def test_is_valid_contact_name():
    """Verify filtering of invalid contact names."""
    from services.contacts import _is_valid_contact_name

    assert _is_valid_contact_name("Rajesh Sharma") is True
    assert _is_valid_contact_name("Solaron Plant 1") is True
    assert _is_valid_contact_name("'+917030605273'") is False
    assert _is_valid_contact_name("1234567890") is False
    assert _is_valid_contact_name("Plant Name") is False
    assert _is_valid_contact_name("Unknown Lead") is False
