#!/usr/bin/env python3
"""
Backfill `Task.name` for tasks missing a name by reading output files
and generating a short summary using the local summarizer.

Usage: python scripts/backfill_task_names.py
Environment: set DATABASE_URL to point to the Postgres DB (or use default sqlite).
"""
import os
from minutes.db import SessionLocal
from minutes.models import Task
from minutes.summary import summarize_local
from pathlib import Path

outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")


def backfill(limit=None):
    session = SessionLocal()
    try:
        q = session.query(Task).filter((Task.name == None) | (Task.name == "")).order_by(Task.created_at.asc())
        if limit:
            q = q.limit(limit)
        updated = 0
        for t in q.all():
            res = t.result or {}
            output_file = None
            if isinstance(res, dict):
                output_file = res.get("output_file") or (res.get("result") or {}).get("output_file")
            if not output_file:
                print(f"skipping {t.id}: no output_file")
                continue
            candidate = Path(outputs_dir) / Path(output_file).name
            if not candidate.exists():
                print(f"skipping {t.id}: output file not found: {candidate}")
                continue
            text = candidate.read_text(encoding='utf-8')
            short = summarize_local(text, max_sentences=1).strip()
            if not short:
                print(f"skipping {t.id}: empty summary")
                continue
            if len(short) > 120:
                short = short[:117].rstrip() + "..."
            t.name = short
            session.add(t)
            session.commit()
            updated += 1
            print(f"updated {t.id} -> {short}")
        print(f"done: updated {updated} tasks")
    finally:
        session.close()


if __name__ == '__main__':
    backfill()
