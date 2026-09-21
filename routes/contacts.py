import logging
from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from helpers import _build_response_data, _config_payload
from services.contacts import (
    get_cache_size,
    get_phone_number,
    import_contacts_from_csv,
    update_contact,
)
from state import get_state, update_state

logger = logging.getLogger(__name__)
router = APIRouter()


class UpdateContactRequest(BaseModel):
    plant_name: str
    phone: str


@router.post("/api/contacts/update")
def update_contact_endpoint(req: UpdateContactRequest):
    """
    Directly add or update a contact's phone number.
    Immediately persists to phone_cache.json, contacts.csv, and in-memory fleet state.
    """
    if not req.plant_name or not req.plant_name.strip():
        return JSONResponse(
            {"success": False, "error": "Plant name is required."},
            status_code=400,
        )

    res = update_contact(req.plant_name, req.phone)
    if not res.get("success"):
        return JSONResponse(res, status_code=400)

    # Invalidate cached response data and re-evaluate
    update_state(response_data=None)
    data, counts = _build_response_data()

    # Find the updated plant record
    updated_record = None
    for plist in data.values():
        for p in plist:
            if p.get("plant_name", "").strip().lower() == req.plant_name.strip().lower():
                updated_record = p
                break
        if updated_record:
            break

    res["plant"] = updated_record
    return res


@router.post("/api/contacts/import-csv")
async def import_contacts_csv_endpoint(file: UploadFile = File(...)):
    """
    Bulk-import contacts from a user-uploaded CSV file.
    Validates mobile numbers, updates phone cache, and synchronizes fleet plants.
    """
    try:
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="ignore")

        res = import_contacts_from_csv(text)
        if not res.get("success"):
            return JSONResponse(res, status_code=400)

        # Invalidate cached response data and re-evaluate
        update_state(response_data=None)
        data, counts = _build_response_data()

        # Count fleet phone match stats
        fleet_with_phone = 0
        total_fleet = 0
        for plist in data.values():
            for p in plist:
                total_fleet += 1
                if p.get("phone"):
                    fleet_with_phone += 1

        res["fleet_with_phone"] = fleet_with_phone
        res["total_fleet"] = total_fleet
        res["data"] = data
        res["counts"] = counts
        return res
    except Exception as exc:
        logger.exception("Error during contact CSV import: %s", exc)
        return JSONResponse(
            {"success": False, "error": f"Failed to import CSV: {str(exc)}"},
            status_code=500,
        )


@router.get("/api/contacts")
def get_contacts_summary():
    """Return contacts cache statistics."""
    size = get_cache_size()
    return {
        "success": True,
        "total_contacts": size,
    }
