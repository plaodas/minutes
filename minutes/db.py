import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from minutes.models import Base
from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("BG_TASK_DB_URL")
if not DATABASE_URL:
    # fallback to a local sqlite file for safety
    DATABASE_URL = f"sqlite:///./data/bg_tasks.sqlite"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ensure tables exist when using sqlite/local development
Base.metadata.create_all(bind=engine)

# Ensure `name` column exists in `tasks` table for running against Postgres
# or older SQLite DBs. Try to add the column if it's missing; ignore errors.
try:
    with engine.connect() as conn:
        # Postgres supports IF NOT EXISTS; SQLite may not, so fall back to plain ALTER
        try:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS name VARCHAR"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN name VARCHAR"))
            except Exception:
                # best-effort: ignore if column already exists or not supported
                pass
except Exception:
    pass
