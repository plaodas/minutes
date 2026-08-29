#!/usr/bin/env python3
import os
import sys
from alembic.config import Config
from alembic import command


def main():
    # Ensure alembic package is importable
    try:
        import alembic  # noqa: F401
    except Exception as e:
        print('alembic import failed:', e)
        sys.exit(2)

    cfg = Config(os.path.join(os.getcwd(), 'alembic.ini'))
    # set sqlalchemy.url from env if present
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        cfg.set_main_option('sqlalchemy.url', db_url)

    print('Running alembic upgrade head...')
    command.upgrade(cfg, 'head')
    print('Alembic upgrade complete')


if __name__ == '__main__':
    main()
