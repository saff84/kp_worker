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
    args = parser.parse_args()

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email)):
            raise SystemExit(f"User already exists: {args.email}")
        user = User(
            email=args.email.strip(),
            password_hash=hash_password(args.password),
            full_name=args.name.strip() or None,
        )
        db.add(user)
        db.commit()
        print(f"Created user {args.email}")
        print("Grant admin UI/API: add this email to ADMIN_EMAILS in .env and restart the API.")


if __name__ == "__main__":
    main()
