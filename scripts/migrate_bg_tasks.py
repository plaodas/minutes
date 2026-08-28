"""Migrate existing data/bg_tasks.json into the `tasks` table.

Usage:
  DATABASE_URL=... python scripts/migrate_bg_tasks.py
"""
import os
import os
import json
import uuid
from sqlalchemy.orm import Session
from minutes.db import engine, SessionLocal
from minutes.models import Task
from datetime import datetime

DB_FILE = os.environ.get('BG_TASK_DB', 'data/bg_tasks.json')

def load_file(path):
    if not os.path.exists(path):
        print('no file to migrate:', path)
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def migrate():
    data = load_file(DB_FILE)
    if not data:
        print('no tasks found')
        return
    session = SessionLocal()
    try:
        for tid, item in data.items():
            print('migrating', tid)
            # create or update existing
            t = session.get(Task, uuid.UUID(tid))
            if not t:
                t = Task(id=uuid.UUID(tid))
                session.add(t)
            t.status = item.get('status')
            t.result = item.get('result')
            t.fail_count = int(item.get('fail_count') or 0)
            # parse timestamps if present
            lf = item.get('last_failure_ts')
            ls = item.get('last_success_ts')
            try:
                if lf:
                    t.last_failure_ts = datetime.fromisoformat(lf.replace('Z', ''))
            except Exception:
                pass
            try:
                if ls:
                    t.last_success_ts = datetime.fromisoformat(ls.replace('Z', ''))
            except Exception:
                pass
            prog = item.get('progress')
            if prog is not None:
                try:
                    t.progress = float(prog)
                except Exception:
                    t.progress = None
        session.commit()
        print('migration complete')
    finally:
        session.close()


if __name__ == '__main__':
    migrate()
