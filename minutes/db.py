import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from minutes.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("BG_TASK_DB_URL")
if not DATABASE_URL:
    # fallback to a local sqlite file for safety
    DATABASE_URL = f"sqlite:///./data/bg_tasks.sqlite"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ensure tables exist when using sqlite/local development
Base.metadata.create_all(bind=engine)
