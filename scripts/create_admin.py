"""Create an admin user in the application's database.

Usage:
    python scripts/create_admin.py --username admin --password secret

If no args provided, reads from environment variables ADMIN_USER and ADMIN_PASS.
"""
import os
import argparse

from minutes.db import SessionLocal
from minutes.models import User
from minutes.auth import get_password_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--username', '-u', default=os.environ.get('ADMIN_USER'))
    p.add_argument('--password', '-p', default=os.environ.get('ADMIN_PASS'))
    args = p.parse_args()

    if not args.username or not args.password:
        print('Provide --username and --password (or set ADMIN_USER/ADMIN_PASS)')
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == args.username).one_or_none()
        if existing:
            print('User already exists:', existing.username)
            return

        u = User(username=args.username, password_hash=get_password_hash(args.password), is_admin=True)
        db.add(u)
        db.commit()
        print('Created admin user:', args.username)
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
