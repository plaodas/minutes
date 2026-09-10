#!/usr/bin/env python3
"""Backfill MinIO buckets into the `buckets` table.

Usage:
  python scripts/backfill_buckets.py [--commit] [--owner OWNER_UUID] [--public]

By default the script runs in dry-run mode and only reports what would be inserted.
If --commit is provided the script will insert missing rows. If --owner is provided
it will be used as owner_id for all inserted rows; otherwise `DUMMY_OWNER_ID` is used.

コンテナから実行する場合：
# dry-run
docker compose exec -T minutes env PYTHONPATH=/app python3 /app/scripts/backfill_buckets.py
# commit
docker compose exec -T minutes env PYTHONPATH=/app python3 /app/scripts/backfill_buckets.py --commit
"""

import argparse
import sys
from minutes.minio_client import MinioService
from minutes.db import session_scope
from minutes.models import Bucket, DUMMY_OWNER_ID
from sqlalchemy.exc import IntegrityError
import uuid


def parse_args():
    p = argparse.ArgumentParser(description="Backfill MinIO buckets into DB")
    p.add_argument(
        "--commit",
        action="store_true",
        help="Actually insert missing rows (default: dry-run)",
    )
    p.add_argument(
        "--owner", type=str, help="Owner UUID to assign to created bucket rows"
    )
    p.add_argument(
        "--public", action="store_true", help="Mark created buckets as public"
    )
    return p.parse_args()


def main():
    args = parse_args()
    owner = None
    if args.owner:
        try:
            owner = uuid.UUID(args.owner)
        except Exception as e:
            print(f"Invalid owner UUID: {args.owner}", file=sys.stderr)
            return 2
    else:
        owner = DUMMY_OWNER_ID

    svc = MinioService()
    try:
        buckets = svc.list_buckets()
    except Exception as exc:
        print("Failed to list buckets from MinIO:", exc, file=sys.stderr)
        return 3

    to_create = []
    # gather existing buckets in a short-lived session
    with session_scope() as db:
        for b in buckets:
            # `list_buckets()` yields Bucket objects with attribute `name`
            name = getattr(b, "name", None) or str(b)
            exists = db.query(Bucket).filter(Bucket.name == name).one_or_none()
            if exists:
                print(f"Exists: {name} (id={exists.id})")
            else:
                print(f"Missing: {name}")
                to_create.append(name)

    if not to_create:
        print("No missing buckets to insert")
        return 0

    print("\nSummary:")
    print(f"  buckets found: {len(buckets)}")
    print(f"  missing to insert: {len(to_create)}")

    if not args.commit:
        print("\nDry-run mode: no changes made. Use --commit to insert missing rows.")
        return 0

    # commit mode: insert each bucket in its own short-lived transaction
    created = 0
    for name in to_create:
        try:
            with session_scope() as db:
                b = Bucket(
                    name=name,
                    owner_id=owner,
                    public=bool(args.public),
                    bucket_metadata={},
                )
                db.add(b)
                db.flush()
                created += 1
                print(f"Inserted: {name} -> id={b.id}")
        except IntegrityError:
            print(f"IntegrityError inserting {name} (skipping)")
        except Exception as exc:
            print(f"Error inserting {name}: {exc}", file=sys.stderr)

    print(f"Created {created} buckets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
