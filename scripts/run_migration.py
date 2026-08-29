#!/usr/bin/env python3
"""
Run SQL migrations from `scripts/migrations/*.sql` against DATABASE_URL.

Usage:
  export DATABASE_URL=postgresql://user:pass@host:5432/dbname
  python3 scripts/run_migration.py scripts/migrations/001_add_minutes_text.sql

This script uses SQLAlchemy to obtain a connection and execute the SQL file.
"""
import sys
import os
from sqlalchemy import create_engine, text


def run_sql_file(url: str, path: str):
    engine = create_engine(url)
    with engine.begin() as conn:
        sql = open(path, 'r', encoding='utf-8').read()
        conn.execute(text(sql))


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 scripts/run_migration.py path/to/migration.sql')
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path):
        print('Migration file not found:', path)
        sys.exit(2)
    url = os.environ.get('DATABASE_URL')
    if not url:
        print('Please set DATABASE_URL environment variable')
        sys.exit(2)
    print('Running migration', path, 'against', url)
    run_sql_file(url, path)
    print('Done')


if __name__ == '__main__':
    main()
