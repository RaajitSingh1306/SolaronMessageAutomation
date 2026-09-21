import logging
import os
import uuid

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from config import Config
from helpers import _allowed_file, _build_response_data, _config_payload
from services.classifier import classify_plants
from services.excel import parse_solaron_file
from state import get_state, update_state

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse({"error": "No file selected."}, status_code=400)

    if not _allowed_file(file.filename, file.content_type):
        return JSONResponse(
            {"error": "Invalid file type. Please upload a .xls or .xlsx file."},
            status_code=400,
        )

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(Config.UPLOAD_FOLDER, safe_name)

    content = await file.read()
    if len(content) > Config.MAX_CONTENT_LENGTH:
        return JSONResponse(
            {"error": f"File too large. Maximum size is {Config.MAX_CONTENT_LENGTH // (1024*1024)} MB."},
            status_code=413,
        )

    with open(filepath, "wb") as buffer:
        buffer.write(content)

    logger.info("File saved: %s", filepath)

    try:
        records, month_name, year, xlsx_path = parse_solaron_file(filepath)
        classified = classify_plants(records)

        update_state(
            classified=classified,
            filepath=xlsx_path,
            month_name=month_name,
            year=year,
            response_data=None,
        )

        data, counts = _build_response_data()

        return {
            "success": True,
            "data": data,
            "counts": counts,
            "config": _config_payload(),
        }

    except Exception as exc:
        logger.exception("Error processing uploaded file.")
        return JSONResponse({"error": str(exc)}, status_code=500)
