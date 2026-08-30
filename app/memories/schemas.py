"""Pydantic schemas for Memory operations."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.storage.models import MemoryCategory


class MemoryCreate(BaseModel):
    """Input payload for creating a new memory record."""

    content: str = Field(..., min_length=1, max_length=1000, description="Memory detail/fact text")
    category: MemoryCategory = Field(default=MemoryCategory.PREFERENCE, description="Memory category")
    source_message_id: int | None = Field(default=None, description="Optional ID of origin chat message")


class MemoryUpdate(BaseModel):
    """Input payload for updating an existing memory record."""

    content: str | None = Field(default=None, min_length=1, max_length=1000)
    category: MemoryCategory | None = Field(default=None)
    is_active: bool | None = Field(default=None)


class MemoryRead(BaseModel):
    """Response model for a memory record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    category: MemoryCategory
    is_active: bool
    created_at: datetime
    updated_at: datetime
    source_message_id: int | None = None

