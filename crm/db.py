import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import Config

# Ensure directory exists for CRM database
os.makedirs(os.path.dirname(Config.CRM_DB_PATH), exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{Config.CRM_DB_PATH}"
)

# For PostgreSQL on Supabase or Render, use pooling with pre-ping
if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
    # Fix postgres:// URL prefix for SQLAlchemy 2.0 if needed
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    crm_engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
else:
    crm_engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

CRMSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=crm_engine)
CRMBase = declarative_base()


def get_crm_db():
    """Dependency for CRM database session."""
    db = CRMSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_crm_db():
    """Create all CRM tables in crm_data.db."""
    from . import models  # noqa: F401
    CRMBase.metadata.create_all(bind=crm_engine)
