"""Pydantic schemas for Conversation and Message domain data."""

from datetime import datetime
from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    role: str = Field(default="user", description="Role: user, assistant, system, or tool")
    content: str | None = Field(default=None, description="Text content of the message")
    tool_calls: str | None = Field(default=None, description="JSON string of tool calls requested")
    tool_call_id: str | None = Field(default=None, description="Tool call identifier")
    name: str | None = Field(default=None, description="Tool name if role is tool")
    authorize_destructive: bool = Field(
        default=False,
        description="Explicit user authorization for destructive AI tool calls in this request.",
    )


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str | None = None
    tool_calls: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    title: str | None = Field(default="New Conversation", max_length=200)


class ConversationRead(BaseModel):
    id: int
    title: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
