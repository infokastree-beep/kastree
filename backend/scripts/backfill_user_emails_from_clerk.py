#!/usr/bin/env python3
"""Backfill users.email from Clerk when rows still have @users.clerk.pending placeholders.

Usage (production shell with CLERK_SECRET_KEY + DATABASE_URL_SYNC set):
    cd backend && python scripts/backfill_user_emails_from_clerk.py
    cd backend && python scripts/backfill_user_emails_from_clerk.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.user import User
from app.services.clerk_users import fetch_clerk_user_primary_email


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned updates without writing to the database",
    )
    args = parser.parse_args()

    updated = 0
    skipped = 0
    with SyncSessionLocal() as session:
        users = session.scalars(select(User).order_by(User.created_at)).all()
        for user in users:
            if not user.email.endswith("@users.clerk.pending"):
                continue
            email = fetch_clerk_user_primary_email(user.clerk_user_id)
            if not email:
                print(f"SKIP {user.clerk_user_id}: no email from Clerk API")
                skipped += 1
                continue
            print(f"{'DRY-RUN' if args.dry_run else 'UPDATE'} {user.clerk_user_id}: {user.email} -> {email}")
            if not args.dry_run:
                set_rls_org_id(session, user.org_id)
                user.email = email
                updated += 1
        if not args.dry_run:
            session.commit()

    print(f"Done. updated={updated} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
