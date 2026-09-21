import csv
import json
import logging
import os
import re
from difflib import SequenceMatcher

from config import Config

logger = logging.getLogger(__name__)

_phone_cache: dict[str, str] = {}
_cache_loaded: bool = False


def _clean_phone_number(raw: str) -> str:
    """Sanitize raw phone string to clean 10-digit Indian mobile number."""
    if not raw:
        return ""
    cleaned = str(raw).strip().strip("'\"").strip()
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    if len(digits) == 10:
        return digits
    return ""


def _is_valid_contact_name(name: str) -> bool:
    """Check if the contact name is a real person/entity name, not a header or raw number."""
    if not name:
        return False
    clean = name.strip().strip("'\"")
    if len(clean) < 2 or not any(ch.isalpha() for ch in clean):
        return False
    if clean.lower() in ("plant name", "first name", "last name", "name", "unknown lead", "none", "null"):
        return False
    return True


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def _load_cache() -> None:
    global _phone_cache, _cache_loaded
    if _cache_loaded:
        return
    
    from database import SessionLocal
    from models import PhoneCache
    
    db = SessionLocal()
    try:
        records = db.query(PhoneCache).all()
        _phone_cache = {}
        for r in records:
            _phone_cache[r.plant_name] = r.phone_number
        logger.info("Loaded %d valid cached phone numbers from database.", len(_phone_cache))
    except Exception as exc:
        logger.warning("Could not load phone cache from DB: %s", exc)
    finally:
        db.close()

    _cache_loaded = True


def save_cache() -> None:
    from database import SessionLocal
    from models import PhoneCache

    db = SessionLocal()
    try:
        # Get existing records to only insert new ones or update changed ones
        existing = {r.plant_name: r.phone_number for r in db.query(PhoneCache).all()}
        
        for k, v in _phone_cache.items():
            if _is_valid_contact_name(k) and v and str(v).strip():
                if k not in existing or existing[k] != v:
                    # Update or insert
                    record = db.query(PhoneCache).filter(PhoneCache.plant_name == k).first()
                    if record:
                        record.phone_number = v
                    else:
                        db.add(PhoneCache(plant_name=k, phone_number=v))
        db.commit()
    except Exception as exc:
        logger.warning("Could not save phone cache to DB: %s", exc)
    finally:
        db.close()


_lower_cache: dict[str, str] = {}
_lower_cache_built: bool = False


def _build_lower_cache() -> None:
    global _lower_cache, _lower_cache_built
    if _lower_cache_built:
        return
    _lower_cache = {
        name.lower().strip(): phone
        for name, phone in _phone_cache.items()
        if phone and str(phone).strip() and _is_valid_contact_name(name)
    }
    _lower_cache_built = True


def clear_cache() -> None:
    """Clear in-memory cache."""
    global _phone_cache, _cache_loaded, _lower_cache, _lower_cache_built
    _phone_cache = {}
    _cache_loaded = False
    _lower_cache = {}
    _lower_cache_built = False


def get_cache_size() -> int:
    """Return count of active phone numbers in cache."""
    _load_cache()
    return len(_phone_cache)


def update_contact(plant_name: str, phone: str) -> dict:
    """
    Directly set or update a phone number for a plant or contact.
    Saves to DB immediately.
    """
    _load_cache()
    clean_p = _clean_phone_number(phone)
    if not clean_p:
        return {
            "success": False,
            "error": "Invalid Indian mobile number. Must be 10 digits starting with 6, 7, 8, or 9.",
        }
    if not _is_valid_contact_name(plant_name):
        return {"success": False, "error": "Invalid plant or contact name."}

    name = plant_name.strip()
    _phone_cache[name] = clean_p
    global _lower_cache_built
    _lower_cache_built = False
    
    from database import SessionLocal
    from models import PhoneCache
    db = SessionLocal()
    try:
        record = db.query(PhoneCache).filter(PhoneCache.plant_name == name).first()
        if record:
            record.phone_number = clean_p
        else:
            db.add(PhoneCache(plant_name=name, phone_number=clean_p))
        db.commit()
    except Exception as exc:
        logger.warning("Could not save to DB: %s", exc)
    finally:
        db.close()

    return {
        "success": True,
        "plant_name": name,
        "phone": clean_p,
        "message": f"Updated phone for '{name}' to {clean_p}.",
    }


def import_contacts_from_csv(csv_content: str) -> dict:
    """
    Bulk import contacts from CSV text.
    Supports headers: Plant Name / Name, Phone / Mobile.
    Also supports headerless 2-column CSV (Name, Phone).
    """
    _load_cache()
    lines = [ln for ln in csv_content.strip().splitlines() if ln.strip()]
    if not lines:
        return {"success": False, "error": "CSV content is empty."}

    reader = csv.reader(lines)
    first_row = next(reader, None)
    if not first_row:
        return {"success": False, "error": "No rows found in CSV."}

    # Detect header columns
    col_names = [c.strip().lower() for c in first_row]
    name_idx = -1
    phone_idx = -1

    for i, col in enumerate(col_names):
        if any(h in col for h in ("plant", "name", "customer", "lead")):
            if name_idx == -1:
                name_idx = i
        if any(h in col for h in ("phone", "mobile", "contact", "cell", "whatsapp")):
            if phone_idx == -1:
                phone_idx = i

    rows_to_process = []
    if name_idx != -1 and phone_idx != -1 and name_idx != phone_idx:
        # First row was a header
        rows_to_process = list(reader)
    else:
        # Check if first row is data (2 columns with phone in col 1)
        if len(first_row) >= 2:
            name_idx = 0
            phone_idx = 1
            rows_to_process = [first_row] + list(reader)
        else:
            return {
                "success": False,
                "error": "CSV must have at least two columns: 'Plant Name' and 'Phone Number'.",
            }

    imported = 0
    from database import SessionLocal
    from models import PhoneCache
    db = SessionLocal()

    try:
        existing = {r.plant_name: r for r in db.query(PhoneCache).all()}
        
        for row in rows_to_process:
            if not row or len(row) <= max(name_idx, phone_idx):
                continue
            raw_name = row[name_idx].strip()
            raw_phone = row[phone_idx].strip()
            if not _is_valid_contact_name(raw_name):
                continue
            clean_p = _clean_phone_number(raw_phone)
            if not clean_p:
                continue

            _phone_cache[raw_name] = clean_p
            if raw_name in existing:
                existing[raw_name].phone_number = clean_p
            else:
                new_record = PhoneCache(plant_name=raw_name, phone_number=clean_p)
                db.add(new_record)
                existing[raw_name] = new_record
                
            imported += 1
            
        if imported > 0:
            db.commit()
            global _lower_cache_built
            _lower_cache_built = False
            
    except Exception as exc:
        logger.warning("Error during bulk import to DB: %s", exc)
        db.rollback()
    finally:
        db.close()

    return {
        "success": True,
        "total_rows": len(rows_to_process),
        "valid_imported": imported,
        "message": f"Successfully imported {imported} valid contact(s) from CSV.",
    }



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_phone_number(plant_name: str) -> str:
    """
    Return the phone number for a plant/contact.

    Lookup order:
        1. In-memory cache
        2. Fuzzy / normalized / partial match
        3. "" (empty — send will be skipped)
    """
    _load_cache()

    if not plant_name or not plant_name.strip():
        return ""

    # 1. Exact key match
    if plant_name in _phone_cache:
        return _phone_cache[plant_name]

    # 2. Fuzzy lookup across all cached names
    phone = _fuzzy_lookup(plant_name)
    _phone_cache[plant_name] = phone or ""
    return phone or ""



# ---------------------------------------------------------------------------
# Fuzzy lookup
# ---------------------------------------------------------------------------

_FUZZY_MIN_LEN = 4


def _normalize_name(s: str) -> str:
    s = s.lower().strip()
    # remove capacity / ratings like '6kw', '10 kwp', '3 kw', etc.
    s = re.sub(r"\b\d+\s*k(?:w|wp)?\b", "", s)
    # remove trailing numbers e.g. 'plant 1'
    s = re.sub(r"\b\d+\b", "", s)
    # remove punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    # collapse spaces
    return re.sub(r"\s+", " ", s).strip()


def _fuzzy_lookup(plant_name: str) -> str:
    """
    Search _phone_cache keys for a match against plant_name with high precision.
    """
    _build_lower_cache()
    plant_clean = plant_name.strip()
    plant_lower = plant_clean.lower()
    norm_p = _normalize_name(plant_name)

    # Pass 1: exact (case-insensitive)
    if plant_lower in _lower_cache:
        return _lower_cache[plant_lower]

    if norm_p and norm_p in _lower_cache:
        return _lower_cache[norm_p]

    # Pass 2: normalized match across keys
    if norm_p and len(norm_p) >= _FUZZY_MIN_LEN:
        for name_lower, phone in _lower_cache.items():
            norm_name = _normalize_name(name_lower)
            if norm_name == norm_p:
                return phone

    # Pass 3: Token matching with Jaccard overlap (prevents false empty-set subset matches)
    p_tokens = set(norm_p.split())
    if len(p_tokens) >= 2:
        for name_lower, phone in _lower_cache.items():
            norm_name = _normalize_name(name_lower)
            l_tokens = set(norm_name.split())
            if len(l_tokens) < 2:
                continue
            common = p_tokens.intersection(l_tokens)
            if len(common) >= 2:
                jaccard = len(common) / len(p_tokens.union(l_tokens))
                if jaccard >= 0.65:
                    return phone

    # Pass 4: High-threshold SequenceMatcher similarity (requires close length and ratio >= 0.88)
    best_ratio = 0.0
    best_phone = ""
    for name_lower, phone in _lower_cache.items():
        norm_name = _normalize_name(name_lower)
        if not norm_name or abs(len(norm_p) - len(norm_name)) > 4 or len(norm_p) < _FUZZY_MIN_LEN:
            continue
        ratio = SequenceMatcher(None, norm_p, norm_name).ratio()
        if ratio > best_ratio and ratio >= 0.88:
            best_ratio = ratio
            best_phone = phone

    if best_phone:
        return best_phone

    return ""


