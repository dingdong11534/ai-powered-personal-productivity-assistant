"""
Pydantic schemas for the Project API boundary.

Same three-schema split as app.tasks.schemas (Base/Create/Update/Read)
and the same reasoning: a client creating a project can't set `id` or
`created_at`; an update is naturally partial; the response shape is kept
distinct from the two write shapes even though the fields overlap.

There is no `ProjectDelete`/hard-delete schema — see ProjectService:
archiving (`archive_project`) is the only lifecycle-ending operation
this API exposes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)


class ProjectCreate(ProjectBase):
    """What a client sends to POST /projects."""


class ProjectUpdate(BaseModel):
    """What a client sends to PUT /projects/{id}.

    Partial update, same semantics as TaskUpdate — see that schema's
    docstring. Deliberately has no `archived_at` field: archiving is its
    own endpoint/operation (`POST /projects/{id}/archive`), not something
    that happens to also be settable through a general-purpose update.
    Keeping it out of ProjectUpdate makes "this project just got
    archived" a single, unambiguous, auditable action rather than one of
    many fields a routine edit could silently flip.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)


class ProjectRead(ProjectBase):
    """What the API returns for a project."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    created_at: datetime
    archived_at: datetime | None = None


class ProjectInviteCreate(BaseModel):
    user_id: int = Field(..., description="Unique User ID to invite to this project")


class ProjectMemberRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    username: str
    role: str
    status: str
    is_online: bool = False
    token_usage: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectInviteRead(BaseModel):
    id: int
    project_id: int
    project_name: str
    project_color: str | None = None
    invited_by_id: int | None = None
    invited_by_name: str | None = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

