#!/usr/bin/env python3
"""Fill tasks.search_text from the stored name and result text.

Usage: DATABASE_URL=... python scripts/backfill_search_text.py
"""

from sqlalchemy.exc import SQLAlchemyError

from minutes.db import session_scope
from minutes.models import Task
from minutes.search_text import build_search_text


def backfill() -> None:
    with session_scope() as session:
        rows = session.query(Task.id).order_by(Task.created_at.asc()).all()
        task_ids = [row.id for row in rows]

    updated = 0
    for task_id in task_ids:
        try:
            with session_scope() as session:
                task = session.get(Task, task_id)
                if task is None:
                    continue
                task.search_text = build_search_text(task.name, task.result)
                session.add(task)
                updated += 1
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            print(f"error processing {task_id}: {exc}")
    print(f"done: updated {updated} tasks")


if __name__ == "__main__":
    backfill()
