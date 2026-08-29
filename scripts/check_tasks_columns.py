#!/usr/bin/env python3
import os
from sqlalchemy import create_engine, text


def main():
    url = os.environ.get('DATABASE_URL', 'postgresql://minutes:minutes_password@db:5432/minutes')
    engine = create_engine(url)
    with engine.connect() as conn:
        sql = (
            "SELECT column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_name='tasks' "
            "ORDER BY ordinal_position;"
        )
        rows = conn.execute(text(sql)).fetchall()
        for col, dtype in rows:
            print(f"{col}\t{dtype}")


if __name__ == '__main__':
    main()
