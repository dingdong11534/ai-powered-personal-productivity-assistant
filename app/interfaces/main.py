"""
FastAPI application entrypoint.

WHAT THIS DOES
---------------
Constructs the `app` object uvicorn serves: registers the startup hook
that creates/patches database tables, registers every domain exception
to HTTP status translation, and includes every router (tasks, tags,
projects, habits, pomodoro, reminders, schedule, notifications).

WHY TABLE CREATION LIVES IN A LIFESPAN HANDLER, NOT AT IMPORT TIME
------------------------------------------------------------------------
`create_all_tables()` runs inside `lifespan()`, called once when the app
actually starts serving, not as a side effect of `import
app.interfaces.main`. Tests import this module (indirectly, via
TestClient) far more often than they want tables created/patched against
the real `data/assistant.db`; keeping creation tied to startup, combined
with tests overriding `get_db` to point at an isolated in-memory database
(see tests/conftest.py), means importing this module is always safe and
side-effect-free. See app.storage.database's docstring for what
`create_all_tables()` does. As of Phase 2 it is back to a pure
`Base.metadata.create_all()` doing all the work: every Phase 2 table is
brand new, so there is no existing table needing the kind of additive
column patch Phase 1 needed for `tasks.project_id` (see
docs/architecture.md's "Migrations" section for the full reasoning).

WHY DOMAIN EXCEPTIONS ARE TRANSLATED HERE, NOT IN EACH ROUTE
------------------------------------------------------------------
Routes just call a service method and let its domain exception (e.g.
`TaskNotFoundError`, `DependencyCycleError`) propagate; they don't catch
it and raise an `HTTPException` themselves. Doing every translation once,
here, via `app.add_exception_handler`, means every route that can raise a
given exception gets consistent status-code behavior for free, and
adding another route later doesn't require remembering to repeat a
try/except.

STATUS CODE CHOICES
---------------------
- 404 Not Found: every `*NotFoundError` (task/project/tag/habit/
  pomodoro session/reminder/schedule item/notification missing).
- 400 Bad Request: SelfDependencyError, InvalidTimeRangeError - each
  describes a request that's invalid as written; no server-side state
  could ever make it valid.
- 409 Conflict: DependencyCycleError, DuplicateTagError,
  DuplicateDependencyError, ArchivedProjectError, UnresolvedDependencyError,
  ArchivedHabitError, DuplicateCompletionError, SessionAlreadyEndedError
  - each describes the request conflicting with the *current state* of
  existing data (a cycle would form, a name is taken, an edge/completion
  already exists, the project/habit isn't active, a dependency isn't
  done yet, a session already ended), which is what HTTP 409 means,
  distinct from "the request itself is malformed" (400) or "nothing
  here" (404).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.habits.exceptions import ArchivedHabitError, DuplicateCompletionError, HabitNotFoundError
from app.interfaces.api.habits import router as habits_router
from app.interfaces.api.notifications import router as notifications_router
from app.interfaces.api.pomodoro import router as pomodoro_router
from app.interfaces.api.projects import router as projects_router
from app.interfaces.api.reminders import router as reminders_router
from app.interfaces.api.schedule import router as schedule_router
from app.interfaces.api.tags import router as tags_router
from app.interfaces.api.tasks import router as tasks_router
from app.notifications.exceptions import NotificationNotFoundError
from app.pomodoro.exceptions import PomodoroSessionNotFoundError, SessionAlreadyEndedError
from app.projects.exceptions import ArchivedProjectError, ProjectNotFoundError
from app.reminders.exceptions import ReminderNotFoundError
from app.scheduling.exceptions import InvalidTimeRangeError, ScheduleItemNotFoundError
from app.storage.database import create_all_tables
from app.tasks.exceptions import (
    DependencyCycleError,
    DuplicateDependencyError,
    DuplicateTagError,
    SelfDependencyError,
    TagNotFoundError,
    TaskNotFoundError,
    UnresolvedDependencyError,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_all_tables()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)


def _json_error(status_code: int):
    def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


NOT_FOUND_EXCEPTIONS = (
    TaskNotFoundError,
    ProjectNotFoundError,
    TagNotFoundError,
    HabitNotFoundError,
    PomodoroSessionNotFoundError,
    ReminderNotFoundError,
    ScheduleItemNotFoundError,
    NotificationNotFoundError,
)
BAD_REQUEST_EXCEPTIONS = (SelfDependencyError, InvalidTimeRangeError)
CONFLICT_EXCEPTIONS = (
    DependencyCycleError,
    DuplicateTagError,
    DuplicateDependencyError,
    ArchivedProjectError,
    UnresolvedDependencyError,
    ArchivedHabitError,
    DuplicateCompletionError,
    SessionAlreadyEndedError,
)

for exc_type in NOT_FOUND_EXCEPTIONS:
    app.add_exception_handler(exc_type, _json_error(404))
for exc_type in BAD_REQUEST_EXCEPTIONS:
    app.add_exception_handler(exc_type, _json_error(400))
for exc_type in CONFLICT_EXCEPTIONS:
    app.add_exception_handler(exc_type, _json_error(409))


app.include_router(tasks_router)
app.include_router(tags_router)
app.include_router(projects_router)
app.include_router(habits_router)
app.include_router(pomodoro_router)
app.include_router(reminders_router)
app.include_router(schedule_router)
app.include_router(notifications_router)

# Phase 3: Static Files and Web UI Dashboard
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def read_index() -> FileResponse:
    """Serve the Phase 3 web UI index page."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        return JSONResponse(status_code=404, content={"detail": "Index HTML not found"})
    return FileResponse(index_path)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check - not part of the task API, useful for confirming
    the server is up before poking at real endpoints."""
    return {"status": "ok"}
