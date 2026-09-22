"""
Task API routes.

Deliberately thin: each function parses input (via the type-hinted
Pydantic schema or query parameters, which FastAPI validates
automatically before the function body even runs), calls exactly one
service method, and returns the result. No SQLAlchemy, no session
handling, no business rules here — see app.tasks.service,
app.tasks.tag_service, and app.tasks.dependency_service for those.

Route paths use "" rather than "/" for the collection endpoints, same
reasoning as app.interfaces.api.projects.

Tag and dependency routes are nested under `/tasks/{task_id}/...` since
they act on a specific task's associations; tag *creation* itself
(`POST /tags`, `GET /tags`) lives in app.interfaces.api.tags instead,
since creating a tag isn't an action on any particular task.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.storage.database import get_db
from app.storage.models import TaskStatus
from app.tasks.dependency_service import TaskDependencyService
from app.tasks.schemas import (
    TagRead,
    TaskCreate,
    TaskDependencyCreate,
    TaskRead,
    TaskUpdate,
)
from app.tasks.service import TaskService
from app.tasks.tag_service import TagService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)


def get_tag_service(db: Session = Depends(get_db)) -> TagService:
    return TagService(db)


def get_dependency_service(db: Session = Depends(get_db)) -> TaskDependencyService:
    return TaskDependencyService(db)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    return service.create_task(data)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    status_: TaskStatus | None = Query(default=None, alias="status"),
    priority: int | None = Query(default=None, ge=1, le=4),
    project_id: int | None = Query(default=None),
    tag_id: int | None = Query(default=None),
    deadline_before: datetime | None = Query(default=None),
    deadline_after: datetime | None = Query(default=None),
    completed: bool | None = Query(default=None),
    search: str | None = Query(default=None, description="Substring match on title/description."),
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    return service.list_tasks(
        skip=skip,
        limit=limit,
        status=status_,
        priority=priority,
        project_id=project_id,
        tag_id=tag_id,
        deadline_before=deadline_before,
        deadline_after=deadline_after,
        completed=completed,
        search=search,
    )


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, service: TaskService = Depends(get_task_service)) -> TaskRead:
    return service.get_task(task_id)


@router.put("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int, data: TaskUpdate, service: TaskService = Depends(get_task_service)
) -> TaskRead:
    return service.update_task(task_id, data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_task(task_id: int, service: TaskService = Depends(get_task_service)) -> Response:
    service.delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Tags on a task ---


@router.get("/{task_id}/tags", response_model=list[TagRead])
def list_task_tags(task_id: int, service: TagService = Depends(get_tag_service)) -> list[TagRead]:
    return service.get_task_tags(task_id)


@router.post("/{task_id}/tags/{tag_id}", response_model=TaskRead)
def attach_tag(
    task_id: int, tag_id: int, service: TagService = Depends(get_tag_service)
) -> TaskRead:
    return service.attach_tag_to_task(task_id, tag_id)


@router.delete("/{task_id}/tags/{tag_id}", response_model=TaskRead)
def detach_tag(
    task_id: int, tag_id: int, service: TagService = Depends(get_tag_service)
) -> TaskRead:
    return service.detach_tag_from_task(task_id, tag_id)


# --- Dependencies on a task ---


@router.get("/{task_id}/dependencies", response_model=list[int])
def list_task_dependencies(
    task_id: int, service: TaskDependencyService = Depends(get_dependency_service)
) -> list[int]:
    return service.list_dependencies(task_id)


@router.post(
    "/{task_id}/dependencies",
    status_code=status.HTTP_201_CREATED,
)
def add_task_dependency(
    task_id: int,
    data: TaskDependencyCreate,
    service: TaskDependencyService = Depends(get_dependency_service),
) -> dict[str, int]:
    dependency = service.add_dependency(task_id, data.depends_on_task_id)
    return {"task_id": dependency.task_id, "depends_on_task_id": dependency.depends_on_task_id}


@router.delete(
    "/{task_id}/dependencies/{depends_on_task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_task_dependency(
    task_id: int,
    depends_on_task_id: int,
    service: TaskDependencyService = Depends(get_dependency_service),
) -> Response:
    service.remove_dependency(task_id, depends_on_task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
