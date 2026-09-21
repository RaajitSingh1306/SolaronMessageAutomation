import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import Config
from database import Base, get_db

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """
    Override the database connection to use an in-memory SQLite DB for tests.
    """
    monkeypatch.setattr("config.Config.DATA_FOLDER", str(tmp_path))
    
    # Create in-memory engine
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Ensure models are loaded so Base.metadata knows about them
    import models
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Patch the SessionLocal in database module
    monkeypatch.setattr("database.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("database.engine", engine)
    
    # Also patch everywhere that imports SessionLocal from database directly
    # To be safe, any module doing `from database import SessionLocal` needs the mock, 
    # but monkeypatching `database.SessionLocal` will work if we use it via `database.SessionLocal()` 
    # Let's hope they do `from database import SessionLocal; SessionLocal()`.
    
    yield
    
    Base.metadata.drop_all(bind=engine)
