#!/usr/bin/env python3
"""
Backfill `Task.name` for tasks missing a name by reading output files
and generating a short summary using the local summarizer.

Usage: python scripts/backfill_task_names.py
Environment: set DATABASE_URL to point to the Postgres DB (or use default sqlite).
"""

import os
from pathlib import Path

from minutes.db import session_scope
from minutes.models import Task
from minutes.summary import summarize_local

outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")


def backfill(limit=None):
    # collect candidate task ids first in a short-lived session
    with session_scope() as db:
        q = (
            db.query(Task.id)
            .filter((Task.name == None) | (Task.name == ""))
            .order_by(Task.created_at.asc())
        )
        if limit:
            q = q.limit(limit)
        ids = [r.id for r in q.all()]

    updated = 0
    for tid in ids:
        try:
            with session_scope() as session:
                t = session.get(Task, tid)
                if not t:
                    print(f"skipping {tid}: not found")
                    continue
                res = t.result or {}
                output_file = None
                if isinstance(res, dict):
                    output_file = res.get("output_file") or (
                        res.get("result") or {}
                    ).get("output_file")
                if not output_file:
                    print(f"skipping {t.id}: no output_file")
                    continue
                candidate = Path(outputs_dir) / Path(output_file).name
                if not candidate.exists():
                    print(f"skipping {t.id}: output file not found: {candidate}")
                    continue
                text = candidate.read_text(encoding="utf-8")
                short = summarize_local(text, max_sentences=1).strip()
                if not short:
                    print(f"skipping {t.id}: empty summary")
                    continue
                if len(short) > 120:
                    short = short[:117].rstrip() + "..."
                t.name = short
                session.add(t)
                session.flush()
                updated += 1
                print(f"updated {t.id} -> {short}")
        except Exception as exc:
            print(f"error processing {tid}: {exc}")

    print(f"done: updated {updated} tasks")


if __name__ == "__main__":
    backfill()
