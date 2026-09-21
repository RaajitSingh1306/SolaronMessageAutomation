import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import Config
from services.excel import PlantRecord

logger = logging.getLogger(__name__)

def _get_cache_path(month: str) -> str:
    """Get the file path for a specific month's cache. (Legacy)"""
    filename = f"growatt_{month}.json"
    return os.path.join(Config.GROWATT_CACHE_DIR, filename)

def is_cache_fresh(month: str) -> bool:
    """
    Check if the cache for the given month exists and was fetched today.
    """
    from database import SessionLocal
    from models import MonthlyGeneration
    db = SessionLocal()
    try:
        record = db.query(MonthlyGeneration).filter(
            MonthlyGeneration.platform == 'growatt',
            MonthlyGeneration.month == month
        ).first()
        if not record:
            return False
            
        fetched_at = record.fetched_at
        return fetched_at.date() == datetime.now().date()
    except Exception as e:
        logger.warning("Error checking cache freshness: %s", e)
        return False
    finally:
        db.close()

def get_cached_data(month: str) -> Optional[Tuple[List[PlantRecord], Dict]]:
    """
    Retrieve cached data for the given month if it's fresh.
    Returns (records, metadata) or None if miss/stale.
    """
    if not is_cache_fresh(month):
        return None
        
    from database import SessionLocal
    from models import MonthlyGeneration
    db = SessionLocal()
    try:
        record = db.query(MonthlyGeneration).filter(
            MonthlyGeneration.platform == 'growatt',
            MonthlyGeneration.month == month
        ).first()
        
        if not record or not record.records_json:
            return None
            
        records_data = json.loads(record.records_json)
        records = []
        for r_dict in records_data:
            rec = PlantRecord(
                plant_name=r_dict.get("plant_name", "Unknown"),
                energy_this_month=r_dict.get("energy_this_month", 0.0),
                energy_this_year=r_dict.get("energy_this_year", 0.0),
                energy_total=r_dict.get("energy_total", 0.0),
                income_this_month=r_dict.get("income_this_month", 0.0),
                income_total=r_dict.get("income_total", 0.0),
                co2_this_month=r_dict.get("co2_this_month", 0.0),
                co2_total=r_dict.get("co2_total", 0.0),
                savings=r_dict.get("savings", 0.0),
                message_status=r_dict.get("message_status", ""),
                nut_bolts=r_dict.get("nut_bolts", ""),
                row_index=r_dict.get("row_index", 0),
                source=r_dict.get("source", "growatt"),
                capacity_kwp=r_dict.get("capacity_kwp", 0.0),
                current_power_kw=r_dict.get("current_power_kw", 0.0),
                energy_today=r_dict.get("energy_today", 0.0),
                plant_status=r_dict.get("plant_status", ""),
                city=r_dict.get("city", ""),
                yearly_breakdown=r_dict.get("yearly_breakdown", {}),
                yearly_history=r_dict.get("yearly_history", {}),
            )
            records.append(rec)
            
        metadata = {
            "fetched_at": record.fetched_at.isoformat() if record.fetched_at else None,
            "plant_count": len(records)
        }
        
        logger.info("Loaded %d plants from cache for %s", len(records), month)
        return records, metadata
    except Exception as e:
        logger.error("Failed to read cache for %s: %s", month, e)
        return None
    finally:
        db.close()

def save_to_cache(month: str, records: List[PlantRecord]) -> None:
    """Save the fetched records to the cache file for the given month."""
    from database import SessionLocal
    from models import MonthlyGeneration
    db = SessionLocal()
    
    try:
        record = db.query(MonthlyGeneration).filter(
            MonthlyGeneration.platform == 'growatt',
            MonthlyGeneration.month == month
        ).first()
        
        records_json = json.dumps([vars(r) for r in records], ensure_ascii=False)
        
        if record:
            record.records_json = records_json
            record.fetched_at = datetime.now(timezone.utc)
        else:
            db.add(MonthlyGeneration(
                platform='growatt',
                month=month,
                records_json=records_json
            ))
            
        db.commit()
        logger.info("Saved %d plants to cache for %s", len(records), month)
    except Exception as e:
        logger.error("Failed to save cache for %s: %s", month, e)
        db.rollback()
    finally:
        db.close()

def clear_cache(month: Optional[str] = None) -> None:
    """Clear cache for a specific month, or all months if None."""
    from database import SessionLocal
    from models import MonthlyGeneration
    db = SessionLocal()
    try:
        if month:
            db.query(MonthlyGeneration).filter(
                MonthlyGeneration.platform == 'growatt',
                MonthlyGeneration.month == month
            ).delete()
            logger.info("Cleared cache for %s", month)
        else:
            db.query(MonthlyGeneration).filter(
                MonthlyGeneration.platform == 'growatt'
            ).delete()
            logger.info("Cleared all growatt cache")
        db.commit()
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        db.rollback()
    finally:
        db.close()
