This folder contains legacy SQL migration scripts that have been
archived after being incorporated into Alembic revisions.

Purpose:
- Keep a copy of ad-hoc SQL migration files for historical reference.
- Do NOT run scripts from this folder in production; prefer `alembic upgrade`.

If you have pending SQL scripts here that are not reflected in
`alembic/versions`, please convert them into Alembic revision files.
