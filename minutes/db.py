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
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Note: do not auto-create or modify schema here. Use Alembic migrations instead.
#
# Configure the engine to pre-ping connections so SQLAlchemy can detect and
# transparently reconnect dropped/stale connections (helps workers recover
# when backends are restarted or individual connections are terminated).
