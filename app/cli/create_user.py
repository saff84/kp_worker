"""Create a user (for production when SEED_DEMO_USERS=false)."""

import argparse

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create login user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="", help="Full name (optional)")
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Grant admin UI and /api/v1/admin/* (stored in DB; no need to list email in ADMIN_EMAILS)",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email)):
            raise SystemExit(f"User already exists: {args.email}")
        user = User(
            email=args.email.strip(),
            password_hash=hash_password(args.password),
            full_name=args.name.strip() or None,
            is_admin=bool(args.admin),
        )
        db.add(user)
        db.commit()
        print(f"Created user {args.email} (is_admin={user.is_admin})")
        if not user.is_admin:
            print("Optional: pass --admin for full admin access, or add email to ADMIN_EMAILS in .env and restart API.")


if __name__ == "__main__":
    main()
