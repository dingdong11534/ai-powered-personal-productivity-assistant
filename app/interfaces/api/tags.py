"""
Tag API routes — creation and listing only.

Attaching/detaching a tag to/from a specific task lives under
`/tasks/{task_id}/tags/...` in app.interfaces.api.tasks instead, since
those are actions on a task's associations, not on the tag itself. See
that module's docstring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.storage.database import get_db
from app.tasks.schemas import TagCreate, TagRead
from app.tasks.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


def get_tag_service(db: Session = Depends(get_db)) -> TagService:
    return TagService(db)


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(data: TagCreate, service: TagService = Depends(get_tag_service)) -> TagRead:
    return service.create_tag(data)


@router.get("", response_model=list[TagRead])
def list_tags(service: TagService = Depends(get_tag_service)) -> list[TagRead]:
    return service.list_tags()
