"""
Pydantic schemas for the Pomodoro API boundary.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PomodoroSessionCreate(BaseModel):
    """What a client sends to POST /pomodoro to start a session.

    `started_at` isn't accepted here — a session always starts "now"
    (see PomodoroSessionService.start_session); unlike a habit
    completion, there's no realistic "log a session after the fact"
    use case for a live focus timer.
    """

    task_id: int | None = Field(default=None, description="Optional task this session is for.")


class PomodoroSessionEnd(BaseModel):
    """What a client sends to POST /pomodoro/{id}/end.

    A single end action with an `interrupted` flag, rather than two
    separate "end" and "interrupt" endpoints — both are the same state
    transition (session stops, `ended_at` is set) differing only in
    whether it finished naturally or was cut short, which the flag
    captures without duplicating the endpoint.
    """

    interrupted: bool = False


class PomodoroSessionRead(BaseModel):
    """What the API returns for a session."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    started_at: datetime
    ended_at: datetime | None
    interrupted: bool
    duration_seconds: int | None
