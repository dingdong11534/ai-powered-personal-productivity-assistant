"""
Pydantic schemas for the Task API boundary.

WHY SEPARATE SCHEMAS FROM THE SQLALCHEMY MODEL
----------------------------------------------------
`app.storage.models.Task` describes a database row. `TaskCreate`,
`TaskUpdate`, and `TaskRead` below describe API *requests and responses*,
which are a different concern even though the fields overlap heavily:

- A client creating a task should never be able to set `id`,
  `created_at`, or `updated_at` — those are server-assigned. `TaskCreate`
  simply doesn't have those fields, so there's no way to even attempt it,
  rather than relying on the route to strip them out.
- An update is naturally partial (change just the status, say) — every
  field on `TaskUpdate` is optional, which would be a strange thing to
  express on the database model itself (`title` being nullable at the DB
  layer would be wrong; it's `NOT NULL` there — see app.storage.models).
- The response shape (`TaskRead`) is what's safe and useful to hand back
  to a client. Right now that happens to be "every column", but keeping
  it a distinct class means adding an internal-only column later (an
  audit flag, say) doesn't automatically leak it through the API.

WHY THREE CLASSES AND NOT ONE
----------------------------------
Collapsing these into one schema class used for both directions is a
common shortcut, but it means either every field has to be optional
(so responses lose the guarantee that `id`/`created_at` are always
present) or every field has to be required (so partial updates become
impossible without sending the whole object back). Three small classes,
sharing a common `TaskBase`, keep each direction's actual constraints
visible in the type itself.

HOW TO TEST
------------
Exercised indirectly through tests/test_tasks_api.py, which sends real
request payloads through these schemas via the FastAPI TestClient — that
catches validation behavior (e.g. rejecting priority=9) the way a real
client would trigger it, rather than testing Pydantic in isolation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.storage.models import TaskStatus


class TaskBase(BaseModel):
    """Fields shared by create and read — not used directly."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: int = Field(default=2, ge=1, le=4, description="1=low .. 4=urgent")
    deadline: datetime | None = None


class TaskCreate(TaskBase):
    """What a client sends to POST /tasks.

    Only `title` is required; every other field has the same default the
    database column does, so a minimal client can create a task with
    nothing but a title.
    """


class TaskUpdate(BaseModel):
    """What a client sends to PUT /tasks/{id}.

    Every field is optional: this is implemented as a partial update —
    only fields the client actually sends are changed (see
    TaskService.update_task, which uses `model_dump(exclude_unset=True)`
    for exactly this reason). Strict REST semantics treat PUT as a full
    replace and PATCH as partial, but for a single-user local app with a
    single client (this project's own API, at least through the phases
    the AI layer will drive it), a partial-update PUT removes friction
    with no real downside — there's no other client relying on
    replace-the-whole-resource semantics. Revisit this if the API grows
    external clients that assume strict PUT.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=4)
    deadline: datetime | None = None


class TaskRead(TaskBase):
    """What the API returns for a task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
