"""
Schedule API routes.

ROUTE ORDERING MATTERS HERE: `/schedule/conflicts` is registered
*before* `/schedule/{item_id}`. FastAPI/Starlette matches routes in
registration order, and `{item_id}` would otherwise greedily match the
literal path segment "conflicts" first (as a string, before FastAPI's
`int` conversion fails on it) — putting the more specific static route
first is what makes `GET /schedule/conflicts?...` reach the intended
handler instead of a 422 from the `{item_id}` route trying to parse
"conflicts" as an int.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.scheduling.schemas import ScheduleItemCreate, ScheduleItemRead, ScheduleItemUpdate
from app.scheduling.service import ScheduleService
from app.storage.database import get_db

router = APIRouter(prefix="/schedule", tags=["schedule"])


def get_schedule_service(db: Session = Depends(get_db)) -> ScheduleService:
    return ScheduleService(db)


@router.post("", response_model=ScheduleItemRead, status_code=status.HTTP_201_CREATED)
def create_schedule_item(
    data: ScheduleItemCreate, service: ScheduleService = Depends(get_schedule_service)
) -> ScheduleItemRead:
    return service.create_schedule_item(data)


@router.get("", response_model=list[ScheduleItemRead])
def list_schedule_items(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleItemRead]:
    return service.list_schedule_items(skip=skip, limit=limit)


# Static route registered before the dynamic "/{item_id}" below — see module docstring.
@router.get("/conflicts", response_model=list[ScheduleItemRead])
def get_conflicts(
    starts_at: datetime | None = Query(default=None),
    ends_at: datetime | None = Query(default=None),
    exclude_id: int | None = Query(default=None),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleItemRead]:
    if starts_at is not None and ends_at is not None:
        return service.find_conflicts(starts_at, ends_at, exclude_id=exclude_id)
    if starts_at is None and ends_at is None:
        return service.find_all_conflicts()
    from app.scheduling.exceptions import InvalidTimeRangeError

    raise InvalidTimeRangeError()


@router.get("/{item_id}", response_model=ScheduleItemRead)
def get_schedule_item(
    item_id: int, service: ScheduleService = Depends(get_schedule_service)
) -> ScheduleItemRead:
    return service.get_schedule_item(item_id)


@router.put("/{item_id}", response_model=ScheduleItemRead)
def update_schedule_item(
    item_id: int,
    data: ScheduleItemUpdate,
    service: ScheduleService = Depends(get_schedule_service),
) -> ScheduleItemRead:
    return service.update_schedule_item(item_id, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_schedule_item(
    item_id: int, service: ScheduleService = Depends(get_schedule_service)
) -> Response:
    service.delete_schedule_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
