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
