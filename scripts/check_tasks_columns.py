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
        out_lines = [f"{col}\t{dtype}" for col, dtype in rows]
        # print to stdout
        for l in out_lines:
            print(l)
        # also write to a file in the project root so host can read it
        try:
            with open(os.path.join(os.getcwd(), 'alembic_tasks_columns.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(out_lines) + '\n')
        except Exception:
            pass


if __name__ == '__main__':
    main()
