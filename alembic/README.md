Alembic migration skeleton for the project.

Quick start:

1. Install dependencies:

```bash
pip install alembic sqlalchemy psycopg2-binary
```

2. Set your database URL (Postgres example):

```bash
export DATABASE_URL=postgresql://user:password@localhost/minutes
```

3. Initialize / run migrations (using the provided initial revision):

```bash
alembic -c alembic.ini upgrade head
```

Notes:
- `alembic/env.py` imports `minutes.models.Base` for `target_metadata`.
- If you change model module path, update `env.py` accordingly.

Recommended workflow
--------------------

1) Install dependencies (locally) or inside the `minutes` container:

```bash
# locally (venv)
python3 -m pip install -r requirements.txt

# or inside the compose container that runs the app
docker compose exec minutes bash -lc "python3 -m pip install -r requirements.txt"
```

2) Apply migrations (examples)

```bash
# preferred: run via Alembic directly
alembic -c alembic.ini upgrade head

# or use the provided programmatic runner (reads DATABASE_URL env):
python3 scripts/run_alembic_head.py

# inside the minutes container (avoids host/network DNS issues):
docker compose exec minutes python3 scripts/run_alembic_head.py
```

3) Create a new revision

```bash
# create an empty revision
alembic -c alembic.ini revision -m "add new column"

# create an autogenerate revision (requires `env.py` to expose target metadata)
alembic -c alembic.ini revision --autogenerate -m "autogen"
```

Tips & troubleshooting
----------------------
- If your Postgres DB runs inside Docker Compose, run Alembic from inside the same compose network (use `docker compose exec minutes ...`) to avoid "could not translate host name 'db'" errors.
- If `alembic` is not available in the container, install it via `pip install alembic` or `pip install -r requirements.txt`.
- If you prefer to run raw SQL migrations, the file `scripts/migrations/001_add_minutes_text.sql` is included as an example.

Safety
------
- Migration scripts in `alembic/versions/` use idempotent SQL where possible (e.g., `IF NOT EXISTS`). Review generated SQL before applying to production databases.

