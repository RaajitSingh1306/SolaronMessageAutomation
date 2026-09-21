from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base

def _utc_now():
    return datetime.now(timezone.utc)

class PhoneCache(Base):
    __tablename__ = "phone_cache"
    id = Column(Integer, primary_key=True, index=True)
    plant_name = Column(String, index=True, unique=True)
    phone_number = Column(String)
    resolved_at = Column(DateTime, default=_utc_now)

class MonthlyGeneration(Base):
    __tablename__ = "monthly_generation"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, index=True)  # 'growatt', 'isolarcloud', 'suryalog'
    month = Column(String, index=True)     # 'YYYY-MM'
    # We will serialize the list of PlantRecord objects as a JSON string to easily transition
    records_json = Column(String)
    fetched_at = Column(DateTime, default=_utc_now)

class DailyGeneration(Base):
    __tablename__ = "daily_generation"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, index=True)
    plant_name = Column(String, index=True)
    # Storing history data as JSON string for easy transition
    history_json = Column(String)
    fetched_at = Column(DateTime, default=_utc_now)

class MessageLog(Base):
    __tablename__ = "message_logs"
    id = Column(Integer, primary_key=True, index=True)
    sent_at = Column(DateTime, default=_utc_now)
    # Storing the results dict as JSON string
    results_json = Column(String)

class PlantSendRecord(Base):
    __tablename__ = "plant_send_records"
    id = Column(Integer, primary_key=True, index=True)
    plant_name = Column(String, index=True)
    month = Column(String, index=True)  # Format: "YYYY-MM"
    phone = Column(String)
    status = Column(String, default="Done")  # "Done"
    sent_at = Column(DateTime, default=_utc_now)
