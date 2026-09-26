"""
PomodoroSessionRepository — direct, ORM-level CRUD against
`pomodoro_sessions`. Same "dumb, no business rules" role as every other
repository in this project.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import PomodoroSession


class PomodoroSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, session: PomodoroSession) -> PomodoroSession:
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get(self, session_id: int) -> PomodoroSession | None:
        return self.db.get(PomodoroSession, session_id)

    def list(
        self, *, skip: int = 0, limit: int = 100, task_id: int | None = None
    ) -> list[PomodoroSession]:
        stmt = (
            select(PomodoroSession)
            .order_by(PomodoroSession.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if task_id is not None:
            stmt = stmt.where(PomodoroSession.task_id == task_id)
        return list(self.db.scalars(stmt))

    def update(self, session: PomodoroSession, changes: dict) -> PomodoroSession:
        for field, value in changes.items():
            setattr(session, field, value)
        self.db.commit()
        self.db.refresh(session)
        return session

    def delete(self, session: PomodoroSession) -> None:
        self.db.delete(session)
        self.db.commit()
