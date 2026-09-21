import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Tuple

from config import Config
from services.contacts import get_phone_number, save_cache
from services.messaging import generate_message, get_whatsapp_web_url
from state import get_state, update_state

logger = logging.getLogger(__name__)

def _allowed_file(filename: str, content_type: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS and (
        content_type in Config.ALLOWED_MIMES or content_type == ""
    )

def _config_payload() -> dict:
    state = get_state()
    return {
        "price_per_unit": Config.PRICE_PER_UNIT,
        "month_name": state.month_name,
        "year": state.year,
        "test_phone_number": Config.TEST_PHONE_NUMBER,
        "support_phone": Config.SUPPORT_PHONE,
    }

def _append_send_log(results: dict) -> None:
    from database import SessionLocal
    from models import MessageLog
    db = SessionLocal()
    try:
        log_entry = MessageLog(
            sent_at=datetime.fromtimestamp(time.time()),
            results_json=json.dumps(results, ensure_ascii=False)
        )
        db.add(log_entry)
        db.commit()
        
        # Keep only the last 5000 records
        count = db.query(MessageLog).count()
        if count > 5000:
            # Delete older records
            oldest_to_keep = db.query(MessageLog).order_by(MessageLog.id.desc()).offset(5000).limit(1).scalar()
            if oldest_to_keep:
                db.query(MessageLog).filter(MessageLog.id <= oldest_to_keep.id).delete()
                db.commit()
                
    except Exception as exc:
        logger.warning("Could not write send log to DB: %s", exc)
        db.rollback()
    finally:
        db.close()

def _build_response_data() -> Tuple[Dict, Dict]:
    state = get_state()
    if state.response_data is not None:
        return state.response_data

    # Query permanent send history from SQLite for the active month
    month_str = getattr(state, "month", None)
    if not month_str and state.year and state.month_name:
        try:
            m_num = datetime.strptime(state.month_name[:3], "%b").month
            month_str = f"{state.year}-{m_num:02d}"
        except Exception:
            pass
    if not month_str:
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")

    from services.send_tracker import get_sent_plants_map
    from services.history import enrich_records_with_daily_history
    from services.deviation import compute_deviations

    # Collect all records across classified lists
    all_recs = []
    for plant_list in state.classified.values():
        all_recs.extend(plant_list)

    enrich_records_with_daily_history(all_recs)
    compute_deviations(all_recs)

    sent_map = get_sent_plants_map(month_str)

    data: dict = {}
    counts: dict = {}
    for status, plants in state.classified.items():
        data[status] = []
        counts[status] = len(plants)
        for p in plants:
            try:
                phone = get_phone_number(p.plant_name)
            except Exception as e:
                logger.warning("Failed to get phone number for %s: %s", p.plant_name, e)
                phone = ""

            message = generate_message(p, status, state.month_name, state.year)
            whatsapp_url = get_whatsapp_web_url(phone, message) if phone and message else ""

            # Check if permanently recorded as Sent in SQLite or Excel
            is_sent = (getattr(p, "message_status", "").strip().lower() in ("done", "sent")) or (p.plant_name in sent_map)
            final_status = "Done" if is_sent else (getattr(p, "message_status", "") or "")
            sent_at = sent_map.get(p.plant_name, {}).get("sent_at", "")

            entry = {
                "plant_name": p.plant_name,
                "energy_this_month": p.energy_this_month,
                "energy_this_year": getattr(p, "energy_this_year", 0.0),
                "energy_total": p.energy_total,
                "savings_file": getattr(p, "savings_from_file", getattr(p, "savings", 0.0)),
                "message_status": final_status,
                "sent_at": sent_at,
                "status": status,
                "phone": phone,
                "whatsapp_url": whatsapp_url,
                "message": message,
                "source": getattr(p, "source", "growatt"),
                "capacity_kwp": getattr(p, "capacity_kwp", 0.0),
                "current_power_kw": getattr(p, "current_power_kw", 0.0),
                "energy_today": getattr(p, "energy_today", 0.0),
                "energy_yesterday": getattr(p, "energy_yesterday", 0.0),
                "energy_weekly": getattr(p, "energy_weekly", 0.0),
                "specific_yield": getattr(p, "specific_yield", 0.0),
                "deviation_pct": getattr(p, "deviation_pct", 0.0),
                "z_score": getattr(p, "z_score", 0.0),
                "city": getattr(p, "city", ""),
                "daily_history": getattr(p, "daily_history", {}),
                "yearly_breakdown": getattr(p, "yearly_breakdown", {}),
                "yearly_history": getattr(p, "yearly_history", {}),
                "device_status_code": getattr(p, "device_status_code", 1),
                "fault_code": getattr(p, "fault_code", ""),
            }
            data[status].append(entry)

    try:
        save_cache()
    except Exception as e:
        logger.warning("Could not save phone cache after building response: %s", e)

    update_state(response_data=(data, counts))
    return data, counts
