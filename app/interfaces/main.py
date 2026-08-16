"""
FastAPI application entrypoint.

WHAT THIS DOES
---------------
Constructs the `app` object uvicorn serves: registers the startup hook
that creates/patches database tables, registers every domain exception ->
HTTP status translation, and includes the task, tag, and project routers.

WHY TABLE CREATION LIVES IN A LIFESPAN HANDLER, NOT AT IMPORT TIME
------------------------------------------------------------------------
`create_all_tables()` runs inside `lifespan()`, called once when the app
actually starts serving — not as a side effect of `import
app.interfaces.main`. Tests import this module (indirectly, via
TestClient) far more often than they want tables created/patched against
the real `data/assistant.db`; keeping creation tied to startup, combined
with tests overriding `get_db` to point at an isolated in-memory database
(see tests/conftest.py), means importing this module is always safe and
side-effect-free. See app.storage.database's docstring for what
`create_all_tables()` actually does as of Phase 1 (new tables + the
additive `tasks.project_id` patch for pre-existing databases).

WHY DOMAIN EXCEPTIONS ARE TRANSLATED HERE, NOT IN EACH ROUTE
------------------------------------------------------------------
Routes just call a service method and let its domain exception (e.g.
`TaskNotFoundError`, `DependencyCycleError`) propagate — they don't catch
it and raise an `HTTPException` themselves. Doing every translation once,
here, via `@app.exception_handler`, means every route that can raise a
given exception gets consistent status-code behavior for free, and
adding another route later doesn't require remembering to repeat a
try/except.

STATUS CODE CHOICES
---------------------
- 404 Not Found: *NotFoundError family (task/project/tag missing).
- 400 Bad Request: SelfDependencyError — the request is invalid as
  written, no server-side state could ever make it valid.
- 409 Conflict: DependencyCycleError, DuplicateTagError,
  DuplicateDependencyError, ArchivedProjectError, UnresolvedDependencyError
  — each describes the request conflicting with the *current state* of
  existing data (a cycle would form, a name is taken, an edge already
  exists, the project isn't active, a dependency isn't done yet), which
  is what HTTP 409 means, distinct from "the request itself is malformed"
  (400) or "nothing here" (404).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.interfaces.api.projects import router as projects_router
from app.interfaces.api.tags import router as tags_router
from app.interfaces.api.tasks import router as tasks_router
from app.projects.exceptions import ArchivedProjectError, ProjectNotFoundError
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


NOT_FOUND_EXCEPTIONS = (TaskNotFoundError, ProjectNotFoundError, TagNotFoundError)
BAD_REQUEST_EXCEPTIONS = (SelfDependencyError,)
CONFLICT_EXCEPTIONS = (
    DependencyCycleError,
    DuplicateTagError,
    DuplicateDependencyError,
    ArchivedProjectError,
    UnresolvedDependencyError,
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


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check — not part of the task API, useful for confirming
    the server is up before poking at real endpoints."""
    return {"status": "ok"}
