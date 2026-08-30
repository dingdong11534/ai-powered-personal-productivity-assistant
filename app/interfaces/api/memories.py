"""FastAPI router for Memory management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.storage.database import get_db
from app.memories.schemas import MemoryCreate, MemoryRead, MemoryUpdate
from app.memories.service import MemoryService
from app.storage.models import MemoryCategory

router = APIRouter(prefix="/memories", tags=["Memories"])


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
def create_memory(
    data: MemoryCreate,
    db: Annotated[Session, Depends(get_db)],
) -> MemoryRead:
    svc = MemoryService(db)
    return svc.create_memory(data)


@router.get("", response_model=list[MemoryRead])
def list_memories(
    db: Annotated[Session, Depends(get_db)],
    category: Annotated[MemoryCategory | None, Query(description="Filter by category")] = None,
    include_archived: Annotated[bool, Query(description="Include archived memories")] = False,
) -> list[MemoryRead]:
    svc = MemoryService(db)
    return svc.list_memories(category=category, include_archived=include_archived)


@router.get("/search", response_model=list[MemoryRead])
def search_memories(
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[str, Query(description="Search keyword")],
    category: Annotated[MemoryCategory | None, Query(description="Filter by category")] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="Max returned items")] = 10,
) -> list[MemoryRead]:
    svc = MemoryService(db)
    return svc.retrieve_relevant_memories(query=query, category=category, limit=limit)


@router.get("/{memory_id}", response_model=MemoryRead)
def get_memory(
    memory_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> MemoryRead:
    svc = MemoryService(db)
    return svc.get_memory(memory_id)


@router.put("/{memory_id}", response_model=MemoryRead)
def update_memory(
    memory_id: int,
    data: MemoryUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> MemoryRead:
    svc = MemoryService(db)
    return svc.update_memory(memory_id, data)


@router.post("/{memory_id}/archive", response_model=MemoryRead)
def archive_memory(
    memory_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> MemoryRead:
    svc = MemoryService(db)
    return svc.archive_memory(memory_id)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    svc = MemoryService(db)
    svc.delete_memory(memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
