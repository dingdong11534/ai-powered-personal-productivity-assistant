"""User repository providing direct CRUD for the users table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        clean = username.strip().lower()
        stmt = select(User).where(User.username == clean)
        return self.db.scalars(stmt).first()

    def list(self) -> list[User]:
        stmt = select(User).order_by(User.id.asc())
        return list(self.db.scalars(stmt))

    def update(self, user: User, changes: dict) -> User:
        for field, value in changes.items():
            setattr(user, field, value)
        self.db.commit()
        self.db.refresh(user)
        return user
