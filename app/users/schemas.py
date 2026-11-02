"""Pydantic schemas for User registration, login, and profile representations."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Username or user name for authentication",
        examples=["kunal", "alex"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Plaintext password",
        examples=["123", "kunalreward34"],
    )


class UserLogin(BaseModel):
    username: str = Field(..., description="Username or name of the user")
    password: str = Field(..., description="Password")


class UserRead(BaseModel):
    id: int
    username: str
    role: str
    is_online: bool = False
    token_usage: int = 0
    created_at: str | None = None

    model_config = {"from_attributes": True}


class UserProfilePublic(BaseModel):
    """Public profile of another user: strictly omits preferences, keys, and private data."""
    id: int
    username: str
    role: str
    is_online: bool = False
    token_usage: int | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserRead
    token: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Authenticated successfully"

