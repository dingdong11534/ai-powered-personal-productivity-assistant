"""
Pydantic schemas for the Habit API boundary.

Same three-schema split as app.tasks.schemas/app.projects.schemas
(Base/Create/Update/Read) and the same reasoning — see those modules.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.storage.models import HabitFrequency


class HabitBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    frequency: HabitFrequency
    target_count: int = Field(
        default=1,
        ge=1,
        le=100,
        description="How many completions satisfy one period of this habit's frequency.",
    )


class HabitCreate(HabitBase):
    """What a client sends to POST /habits."""


class HabitUpdate(BaseModel):
    """What a client sends to PUT /habits/{id}. Partial update — same
    semantics as TaskUpdate/ProjectUpdate. No `archived_at` field, same
    reasoning as ProjectUpdate: archiving is its own endpoint
    (`POST /habits/{id}/archive`), not a field a routine edit could
    silently flip.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    frequency: HabitFrequency | None = None
    target_count: int | None = Field(default=None, ge=1, le=100)


class HabitRead(HabitBase):
    """What the API returns for a habit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    archived_at: datetime | None


class HabitCompletionCreate(BaseModel):
    """What a client sends to POST /habits/{id}/complete.

    `completed_at` is optional — omitted, it defaults to now (see
    HabitService.record_completion). Accepting an explicit timestamp
    supports logging a completion after the fact (e.g. "I did this
    yesterday but forgot to log it"), which a habit tracker needs to be
    usable in practice.
    """

    completed_at: datetime | None = None


class HabitCompletionRead(BaseModel):
    """What the API returns for a single completion record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    habit_id: int
    completed_at: datetime
    completed_date: date


class HabitStatisticsRead(BaseModel):
    """What GET /habits/{id}/statistics returns."""

    total_completions: int
    current_streak: int
    longest_streak: int
    periods_since_creation: int
    periods_satisfied: int
    completion_rate: float
