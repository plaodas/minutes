import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from minutes.models import Base
from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("BG_TASK_DB_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL or BG_TASK_DB_URL must be set; refusing to use local sqlite fallback.\n"
        "Set DATABASE_URL to your Postgres DSN in production or configure an explicit local DB for development."
    )

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Note: do not auto-create tables here. Schema migrations must be applied explicitly via Alembic
# to avoid accidental schema drift or silent creation in production environments.

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
