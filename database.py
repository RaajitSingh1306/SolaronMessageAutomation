import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import Config

# Ensure data directory exists
os.makedirs(Config.DATA_FOLDER, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(Config.DATA_FOLDER, 'solaron.db')}"

# connect_args={"check_same_thread": False} is needed for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    import models
    Base.metadata.create_all(bind=engine)
