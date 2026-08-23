"""
PomodoroSessionService — the layer app.interfaces calls for Pomodoro
sessions.

WHAT THIS DOES
---------------
- `start_session`: creates a session with `started_at = now`, validates
  `task_id` if given (must reference an existing task — reuses
  `app.tasks.repository.TaskRepository`, the same cross-domain-read
  pattern `TaskService` already uses against `app.projects` — see that
  module's docstring for why this is a deliberate, one-way exception to
  "domain packages don't depend on each other").
- `end_session`: sets `ended_at = now`, computes and stores
  `duration_seconds`, and sets `interrupted` from the caller's flag.
  Raises `SessionAlreadyEndedError` if the session already has an
  `ended_at` — a session can only be ended once, whether normally or by
  interruption; both go through this one method (see
  `PomodoroSessionEnd`'s docstring for why there's no separate
  "interrupt" method).

HOW TO TEST
------------
See tests/test_pomodoro_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.pomodoro.exceptions import PomodoroSessionNotFoundError, SessionAlreadyEndedError
from app.pomodoro.repository import PomodoroSessionRepository
from app.storage.models import PomodoroSession
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.repository import TaskRepository


class PomodoroSessionService:
    def __init__(self, db: Session) -> None:
        self.repository = PomodoroSessionRepository(db)
        self.tasks = TaskRepository(db)

    def start_session(self, task_id: int | None = None) -> PomodoroSession:
        if task_id is not None and self.tasks.get(task_id) is None:
            raise TaskNotFoundError(task_id)
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session = PomodoroSession(task_id=task_id, started_at=started_at)
        return self.repository.create(session)

    def get_session(self, session_id: int) -> PomodoroSession:
        session = self.repository.get(session_id)
        if session is None:
            raise PomodoroSessionNotFoundError(session_id)
        return session

    def list_sessions(
        self, *, skip: int = 0, limit: int = 100, task_id: int | None = None
    ) -> list[PomodoroSession]:
        return self.repository.list(skip=skip, limit=limit, task_id=task_id)

    def end_session(self, session_id: int, *, interrupted: bool = False) -> PomodoroSession:
        session = self.get_session(session_id)
        if session.ended_at is not None:
            raise SessionAlreadyEndedError(session_id)

        ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_seconds = int((ended_at - session.started_at).total_seconds())
        return self.repository.update(
            session,
            {
                "ended_at": ended_at,
                "interrupted": interrupted,
                "duration_seconds": duration_seconds,
            },
        )
