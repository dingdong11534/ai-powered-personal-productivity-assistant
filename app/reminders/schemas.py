"""
Pydantic schemas for the Reminder API boundary.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReminderBase(BaseModel):
    task_id: int | None = Field(default=None, description="Optional task this reminder is for.")
    remind_at: datetime
    message: str = Field(min_length=1, max_length=500)


class ReminderCreate(ReminderBase):
    """What a client sends to POST /reminders.

    `remind_at` in the past is accepted, not rejected — see
    ReminderService's docstring for why: a past time just means the
    reminder shows up immediately as "due" rather than being scheduled
    for later, which is useful (e.g. logging something that should have
    reminded the user already) rather than harmful.
    """


class ReminderUpdate(BaseModel):
    """What a client sends to PUT /reminders/{id}. Partial update."""

    task_id: int | None = None
    remind_at: datetime | None = None
    message: str | None = Field(default=None, min_length=1, max_length=500)


class ReminderRead(ReminderBase):
    """What the API returns for a reminder."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fired_at: datetime | None
    created_at: datetime
