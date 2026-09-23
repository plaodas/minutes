import os

# Ensure tests can import the app without requiring an external Postgres instance.
# Use an in-memory SQLite DB for test-time imports. Tests that need a real DB
# should override this in their environment or skip accordingly.
os.environ.setdefault("DATABASE_URL", "sqlite:///./.pytest_sqlite.db")

# Create tables for the in-memory SQLite so DB-backed code paths can run in tests.
try:
    # Import lazily so pytest collection can proceed even if SQLAlchemy isn't installed
    from sqlalchemy import inspect, text

    from minutes.db import engine
    from minutes.models import Base

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if inspector.has_table("users"):
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "is_admin" not in user_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_admin BOOLEAN "
                        "NOT NULL DEFAULT 0"
                    )
                )
except (ImportError, OSError):
    # If anything fails (missing deps), tests that require DB will skip at runtime.
    pass
