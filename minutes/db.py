import os
from contextlib import contextmanager
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

# Configure connection pool tuning via environment variables with sensible defaults.
_pool_size = int(os.environ.get("DB_POOL_SIZE", "5"))
_max_overflow = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
_pool_timeout = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
_pool_recycle = int(os.environ.get("DB_POOL_RECYCLE", "1800"))

# For SQLite keep the same check_same_thread behavior; for Postgres set pool params.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=_pool_size,
        max_overflow=_max_overflow,
        pool_timeout=_pool_timeout,
        pool_recycle=_pool_recycle,
    )

# Session factory: avoid expiring objects on commit so callers can read simple
# scalar attributes without reloading; callers should still prefer short-lived
# sessions and not rely on expired-on-access semantics.
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as db:
            db.add(obj)
            # commit happens automatically on success; rollback on exception
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def dispose_engine():
    """Dispose the SQLAlchemy engine (useful to call after fork in Celery)."""
    try:
        engine.dispose()
    except Exception:
        pass


# Note: do not auto-create or modify schema here. Use Alembic migrations instead.
