import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from config import Config
from database import SessionLocal
from models import PlantSendRecord
from state import get_state, update_state
from services.excel.updater import update_excel_status

logger = logging.getLogger(__name__)

def record_successful_sends(
    sent_plants: List[str],
    month_str: Optional[str] = None,
    phone_map: Optional[Dict[str, str]] = None,
) -> None:
    """
    Persistently records sent WhatsApp messages across:
    1. SQLite Database (plant_send_records table)
    2. Active Excel file (uploads/SolarOn - {month}.xlsx or state.filepath)
    3. In-memory state (p.message_status = 'Done')
    """
    if not sent_plants:
        return

    state = get_state()
    if not month_str:
        # Default to state month or current month (YYYY-MM)
        month_str = getattr(state, "month", None)
        if not month_str and state.year and state.month_name:
            # Map month name to number
            try:
                m_num = datetime.strptime(state.month_name[:3], "%b").month
                month_str = f"{state.year}-{m_num:02d}"
            except Exception:
                pass
    if not month_str:
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")

    phone_map = phone_map or {}
    now = datetime.now(timezone.utc)

    # 1. Save to SQLite DB
    db = SessionLocal()
    try:
        for plant_name in sent_plants:
            phone = phone_map.get(plant_name, "")
            # Check if record already exists for this month
            existing = (
                db.query(PlantSendRecord)
                .filter(
                    PlantSendRecord.plant_name == plant_name,
                    PlantSendRecord.month == month_str,
                )
                .first()
            )
            if existing:
                existing.status = "Done"
                existing.sent_at = now
                if phone:
                    existing.phone = phone
            else:
                record = PlantSendRecord(
                    plant_name=plant_name,
                    month=month_str,
                    phone=phone,
                    status="Done",
                    sent_at=now,
                )
                db.add(record)
        db.commit()
        logger.info("Recorded %d sent plants in database for month %s.", len(sent_plants), month_str)
    except Exception as e:
        logger.error("Failed to save plant send records to DB: %s", e)
        db.rollback()
    finally:
        db.close()

    # 2. Update In-Memory State
    if state.classified:
        sent_set = set(sent_plants)
        for plants in state.classified.values():
            for p in plants:
                if p.plant_name in sent_set:
                    p.message_status = "Done"
        # Invalidate response_data cache so fresh status is sent to UI
        update_state(response_data=None)

    # 3. Update Excel File
    excel_path = state.filepath
    if not excel_path or not os.path.exists(excel_path):
        candidate = os.path.join(Config.UPLOAD_FOLDER, f"SolarOn - {month_str}.xlsx")
        if os.path.exists(candidate):
            excel_path = candidate

    if excel_path and os.path.exists(excel_path):
        try:
            sent_plants_with_dummy_row = [(name, 0) for name in sent_plants]
            update_excel_status(excel_path, sent_plants_with_dummy_row)
            logger.info("Updated Excel status to 'Done' for %d plants in %s.", len(sent_plants), excel_path)
        except Exception as exc:
            logger.warning("Could not update Excel file with sent status: %s", exc)


def get_sent_plants_map(month_str: Optional[str] = None) -> Dict[str, dict]:
    """
    Returns a dictionary of all plants marked as sent for the given month:
    { "Plant A": { "status": "Done", "sent_at": "03 Sep 14:44" } }
    """
    if not month_str:
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")

    db = SessionLocal()
    result: Dict[str, dict] = {}
    try:
        records = (
            db.query(PlantSendRecord)
            .filter(
                PlantSendRecord.month == month_str,
                PlantSendRecord.status == "Done",
            )
            .all()
        )
        for r in records:
            sent_time_str = r.sent_at.strftime("%d %b %H:%M") if r.sent_at else ""
            result[r.plant_name] = {
                "status": "Done",
                "sent_at": sent_time_str,
            }
    except Exception as e:
        logger.error("Error retrieving sent plants for month %s: %s", month_str, e)
    finally:
        db.close()
    return result
