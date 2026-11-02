"""
Pydantic schemas for the Notification API boundary.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    """What a client sends to POST /notifications."""

    title: str = Field(min_length=1, max_length=200)
    body: str | None = None
    source: str | None = Field(default=None, max_length=50)


class NotificationRead(BaseModel):
    """What the API returns for a notification."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str | None
    user_id: int | None = None
    created_at: datetime
    read_at: datetime | None
    source: str | None

