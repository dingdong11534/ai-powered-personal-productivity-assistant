"""
Task API routes.

Deliberately thin: each function parses input (via the type-hinted
Pydantic schema, which FastAPI validates automatically before the
function body even runs), calls exactly one TaskService method, and
returns the result. No SQLAlchemy, no session handling, no business
rules here — see app.tasks.service for those.

Route paths use "" rather than "/" for the collection endpoints
(`@router.post("")`, not `@router.post("/")`) so that, combined with
`prefix="/tasks"`, the full paths are exactly `/tasks` and `/tasks`, not
`/tasks/` — avoiding FastAPI's redirect-on-trailing-slash-mismatch for
clients that call `GET /tasks` (no trailing slash), matching the spec's
endpoint list exactly.

get_task_service() is itself a FastAPI dependency (constructed from
get_db()), not a bare function call — that's what lets a test override
get_db (see tests/conftest.py) and have the override apply here without
this file needing to know tests exist.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.storage.database import get_db
from app.tasks.schemas import TaskCreate, TaskRead, TaskUpdate
from app.tasks.service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    return service.create_task(data)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    return service.list_tasks(skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, service: TaskService = Depends(get_task_service)) -> TaskRead:
    return service.get_task(task_id)


@router.put("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int, data: TaskUpdate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    return service.update_task(task_id, data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, service: TaskService = Depends(get_task_service)) -> None:
    service.delete_task(task_id)
