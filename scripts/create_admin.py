"""Create an admin user in the application's database.

Usage:
    python scripts/create_admin.py --username admin --password secret

If no args provided, reads from environment variables ADMIN_USER and ADMIN_PASS.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `minutes` package can be imported
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from minutes.auth import get_password_hash
from minutes.db import session_scope
from minutes.models import User


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--username", "-u", default=os.environ.get("ADMIN_USER"))
    p.add_argument("--password", "-p", default=os.environ.get("ADMIN_PASS"))
    args = p.parse_args()

    if not args.username or not args.password:
        print("Provide --username and --password (or set ADMIN_USER/ADMIN_PASS)")
        return

    with session_scope() as db:
        existing = db.query(User).filter(User.username == args.username).one_or_none()
        if existing:
            print("User already exists:", existing.username)
            return

        u = User(
            username=args.username,
            password_hash=get_password_hash(args.password),
            is_admin=True,
        )
        db.add(u)
        db.flush()
        print("Created admin user:", args.username)


if __name__ == "__main__":
    main()
