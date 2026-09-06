import os

# Ensure tests can import the app without requiring an external Postgres instance.
# Use an in-memory SQLite DB for test-time imports. Tests that need a real DB
# should override this in their environment or skip accordingly.
os.environ.setdefault('DATABASE_URL', 'sqlite:///./.pytest_sqlite.db')

# Create tables for the in-memory SQLite so DB-backed code paths can run in tests.
try:
	# Import lazily so pytest collection can proceed even if SQLAlchemy isn't installed
	from minutes.models import Base
	from minutes.db import engine

	Base.metadata.create_all(bind=engine)
except Exception:
	# If anything fails (missing deps), tests that require DB will skip at runtime.
	pass
