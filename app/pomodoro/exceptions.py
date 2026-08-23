"""Pomodoro domain exceptions. Plain Python exceptions — see
app.tasks.exceptions for why."""

from __future__ import annotations


class PomodoroSessionNotFoundError(Exception):
    """Raised when a session lookup by id finds nothing."""

    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(f"Pomodoro session {session_id} not found")


class SessionAlreadyEndedError(Exception):
    """Raised when trying to end (or interrupt) a session that already
    has an `ended_at` — a session can only be ended once."""

    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(f"Pomodoro session {session_id} has already ended")
