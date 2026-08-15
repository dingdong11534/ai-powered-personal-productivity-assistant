"""
FastAPI application entrypoint.

WHAT THIS DOES
---------------
Constructs the `app` object uvicorn serves: registers the startup hook
that creates database tables, registers the TaskNotFoundError -> HTTP 404
translation, and includes the task router.

WHY TABLE CREATION LIVES IN A LIFESPAN HANDLER, NOT AT IMPORT TIME
------------------------------------------------------------------------
`create_all_tables()` runs inside `lifespan()`, called once when the app
actually starts serving — not as a side effect of `import
app.interfaces.main`. Tests import this module (indirectly, via
TestClient) far more often than they want tables created against the
real `data/assistant.db`; keeping creation tied to startup, combined with
tests overriding `get_db` to point at an isolated in-memory database (see
tests/conftest.py), means importing this module is always safe and side
-effect-free.

WHY TaskNotFoundError IS TRANSLATED HERE, NOT IN THE ROUTE
------------------------------------------------------------------
The route (app/interfaces/api/tasks.py) just calls `service.get_task(id)`
and lets `TaskNotFoundError` propagate — it doesn't catch it and raise an
`HTTPException` itself. Doing the translation once, here, via
`@app.exception_handler`, means every route that can raise
`TaskNotFoundError` (get/update/delete) gets consistent 404 behavior for
free, and adding a tenth route later doesn't require remembering to
repeat a try/except.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.interfaces.api.tasks import router as tasks_router
from app.storage.database import create_all_tables
from app.tasks.exceptions import TaskNotFoundError

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_all_tables()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)


@app.exception_handler(TaskNotFoundError)
def handle_task_not_found(request: Request, exc: TaskNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


app.include_router(tasks_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness check — not part of the task API, useful for confirming
    the server is up before poking at real endpoints."""
    return {"status": "ok"}
