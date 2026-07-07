"""Idempotent first-admin bootstrap: `python -m app.bootstrap`."""
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.models import User


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == settings.first_admin_email.lower()))
        if existing:
            print(f"Admin {settings.first_admin_email} already exists")
            return
        db.add(
            User(
                email=settings.first_admin_email.lower(),
                full_name="System Administrator",
                hashed_password=hash_password(settings.first_admin_password),
                role=UserRole.admin,
            )
        )
        db.commit()
        print(f"Created admin {settings.first_admin_email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
