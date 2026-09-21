import os
import sys
import json
import csv
from datetime import datetime

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db
from models import PhoneCache, MonthlyGeneration, DailyGeneration, MessageLog
from config import Config

def clean_phone_number(num_str: str) -> str:
    """Helper from contacts.py"""
    if not num_str:
        return ""
    digits = "".join(filter(str.isdigit, str(num_str)))
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return ""

def migrate_contacts():
    db = SessionLocal()
    print("Migrating phone cache (contacts)...")
    try:
        # Load phone_cache.json
        cache_path = os.path.join(Config.DATA_FOLDER, "phone_cache.json")
        phone_dict = {}
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                raw_cache = json.loads(f.read())
                for k, v in raw_cache.items():
                    clean_p = clean_phone_number(v)
                    if k.strip() and clean_p:
                        phone_dict[k.strip()] = clean_p
                        
        # Load contacts.csv
        contacts_path = os.path.join(Config.DATA_FOLDER, "contacts.csv")
        if os.path.exists(contacts_path):
            with open(contacts_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0].strip() and not row[0].startswith("#"):
                        name = row[0].strip()
                        phone = clean_phone_number(row[1])
                        if phone and name not in phone_dict:
                            phone_dict[name] = phone
                            
        # Save to DB
        existing = {r.plant_name for r in db.query(PhoneCache).all()}
        inserted = 0
        for name, phone in phone_dict.items():
            if name not in existing:
                db.add(PhoneCache(plant_name=name, phone_number=phone))
                inserted += 1
                
        db.commit()
        print(f"  -> Inserted {inserted} contacts.")
    except Exception as e:
        print(f"  -> Error migrating contacts: {e}")
        db.rollback()
    finally:
        db.close()

def migrate_monthly_cache(platform: str, cache_dir: str):
    db = SessionLocal()
    print(f"Migrating {platform} cache...")
    try:
        if not os.path.exists(cache_dir):
            print(f"  -> Directory {cache_dir} not found.")
            return
            
        existing_months = {
            r.month for r in db.query(MonthlyGeneration).filter(MonthlyGeneration.platform == platform).all()
        }
        
        inserted = 0
        for filename in os.listdir(cache_dir):
            if filename.startswith(f"{platform}_") and filename.endswith(".json"):
                month = filename.replace(f"{platform}_", "").replace(".json", "")
                if month in existing_months:
                    continue
                    
                path = os.path.join(cache_dir, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("records", [])
                    fetched_at_str = data.get("fetched_at")
                    
                    fetched_at = datetime.utcnow()
                    if fetched_at_str:
                        try:
                            fetched_at = datetime.fromisoformat(fetched_at_str)
                        except ValueError:
                            pass
                            
                    db.add(MonthlyGeneration(
                        platform=platform,
                        month=month,
                        records_json=json.dumps(records, ensure_ascii=False),
                        fetched_at=fetched_at
                    ))
                    inserted += 1
                    
        db.commit()
        print(f"  -> Inserted {inserted} monthly cache records.")
    except Exception as e:
        print(f"  -> Error migrating {platform} cache: {e}")
        db.rollback()
    finally:
        db.close()

def migrate_history():
    db = SessionLocal()
    print("Migrating daily/yearly history...")
    try:
        history_path = os.path.join(Config.DATA_FOLDER, "history", "yearly_data.json")
        if not os.path.exists(history_path):
            print("  -> History file not found.")
            return
            
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        plants = data.get("plants", {})
        existing = {
            f"{r.platform}:{r.plant_name}" for r in db.query(DailyGeneration).all()
        }
        
        inserted = 0
        for key, plant_data in plants.items():
            source = plant_data.get("source", "unknown")
            plant_name = plant_data.get("plant_name", "unknown")
            if key not in existing:
                db.add(DailyGeneration(
                    platform=source,
                    plant_name=plant_name,
                    history_json=json.dumps(plant_data, ensure_ascii=False)
                ))
                inserted += 1
                
        db.commit()
        print(f"  -> Inserted {inserted} history records.")
    except Exception as e:
        print(f"  -> Error migrating history: {e}")
        db.rollback()
    finally:
        db.close()

def migrate_send_log():
    db = SessionLocal()
    print("Migrating send log...")
    try:
        log_path = os.path.join(Config.DATA_FOLDER, "send_log.jsonl")
        if not os.path.exists(log_path):
            print("  -> Send log file not found.")
            return
            
        # We don't have a reliable primary key to deduplicate easily, so we just
        # check if the table is empty before migrating.
        count = db.query(MessageLog).count()
        if count > 0:
            print(f"  -> MessageLog table already has {count} records, skipping to avoid duplicates.")
            return
            
        inserted = 0
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    ts = data.get("timestamp")
                    results = data.get("results", {})
                    
                    if ts:
                        sent_at = datetime.fromtimestamp(ts)
                    else:
                        sent_at = datetime.utcnow()
                        
                    db.add(MessageLog(
                        sent_at=sent_at,
                        results_json=json.dumps(results, ensure_ascii=False)
                    ))
                    inserted += 1
                except Exception as ex:
                    print(f"     Failed to parse line: {ex}")
                    
        db.commit()
        print(f"  -> Inserted {inserted} message log records.")
    except Exception as e:
        print(f"  -> Error migrating send log: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Initializing Database...")
    init_db()
    
    print("\n--- Starting Migration ---")
    migrate_contacts()
    migrate_monthly_cache("growatt", Config.GROWATT_CACHE_DIR)
    migrate_monthly_cache("isolarcloud", Config.ISOLARCLOUD_CACHE_DIR)
    migrate_monthly_cache("suryalog", Config.SURYALOG_CACHE_DIR)
    migrate_history()
    migrate_send_log()
    print("--- Migration Complete ---")
