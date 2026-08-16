"""
Project API routes.

Same thin-route discipline as app.interfaces.api.tasks: parse input,
call one ProjectService method, return the result.

No DELETE /projects/{id} route — this API never exposes a hard delete
for projects (see ProjectService). `POST /projects/{id}/archive` is the
only lifecycle-ending action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.projects.service import ProjectService
from app.storage.database import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate, service: ProjectService = Depends(get_project_service)
) -> ProjectRead:
    return service.create_project(data)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    include_archived: bool = Query(
        default=True, description="Set to false to exclude archived projects."
    ),
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectRead]:
    return service.list_projects(skip=skip, limit=limit, include_archived=include_archived)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int, service: ProjectService = Depends(get_project_service)
) -> ProjectRead:
    return service.get_project(project_id)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    return service.update_project(project_id, data)


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: int, service: ProjectService = Depends(get_project_service)
) -> ProjectRead:
    return service.archive_project(project_id)
