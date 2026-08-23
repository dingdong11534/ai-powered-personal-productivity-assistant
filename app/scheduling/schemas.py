"""
Pydantic schemas for the Schedule API boundary.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScheduleItemBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    task_id: int | None = Field(default=None, description="Optional task this block is for.")


class ScheduleItemCreate(ScheduleItemBase):
    """What a client sends to POST /schedule.

    `ends_at > starts_at` is validated in ScheduleService, not here —
    Pydantic field validators can't easily compare two sibling fields
    without a model-level validator, and the project already has a
    consistent place for this kind of cross-field business rule (the
    service layer, backed by a DB CheckConstraint) — see
    app.scheduling.service and app.storage.models.ScheduleItem.
    """


class ScheduleItemUpdate(BaseModel):
    """What a client sends to PUT /schedule/{id}. Partial update.

    If either `starts_at` or `ends_at` changes, the *resulting* range
    (old value for the field not sent, new value for the one that was)
    is re-validated by ScheduleService.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    task_id: int | None = None


class ScheduleItemRead(ScheduleItemBase):
    """What the API returns for a schedule item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
