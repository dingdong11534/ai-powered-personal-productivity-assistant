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

from app.core.auth import check_item_access, get_current_user
from app.notifications.service import record_activity
from app.scheduling.schemas import ScheduleItemCreate, ScheduleItemRead, ScheduleItemUpdate
from app.scheduling.service import ScheduleService
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter(prefix="/schedule", tags=["schedule"])


def get_schedule_service(db: Session = Depends(get_db)) -> ScheduleService:
    return ScheduleService(db)


@router.post("", response_model=ScheduleItemRead, status_code=status.HTTP_201_CREATED)
def create_schedule_item(
    data: ScheduleItemCreate,
    current_user: User = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
    db: Session = Depends(get_db),
) -> ScheduleItemRead:
    item = service.create_schedule_item(data, user_id=current_user.id)
    record_activity(db, f"Schedule added: {item.title}", source="schedule", user_id=current_user.id)
    return item


@router.get("", response_model=list[ScheduleItemRead])
def list_schedule_items(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    all_users: bool = Query(default=False, description="Admin only: list schedule items across all users."),
    current_user: User = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleItemRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    return service.list_schedule_items(skip=skip, limit=limit, user_id=target_user_id)


# Static route registered before the dynamic "/{item_id}" below — see module docstring.
@router.get("/conflicts", response_model=list[ScheduleItemRead])
def get_conflicts(
    starts_at: datetime | None = Query(default=None),
    ends_at: datetime | None = Query(default=None),
    exclude_id: int | None = Query(default=None),
    all_users: bool = Query(default=False, description="Admin only: find conflicts across all users."),
    current_user: User = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleItemRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    if starts_at is not None and ends_at is not None:
        return service.find_conflicts(starts_at, ends_at, exclude_id=exclude_id, user_id=target_user_id)
    if starts_at is None and ends_at is None:
        return service.find_all_conflicts(user_id=target_user_id)
    from app.scheduling.exceptions import InvalidTimeRangeError

    raise InvalidTimeRangeError()


@router.get("/{item_id}", response_model=ScheduleItemRead)
def get_schedule_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> ScheduleItemRead:
    item = service.get_schedule_item(item_id)
    check_item_access(item.user_id, current_user, "view")
    return item


@router.put("/{item_id}", response_model=ScheduleItemRead)
def update_schedule_item(
    item_id: int,
    data: ScheduleItemUpdate,
    current_user: User = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
) -> ScheduleItemRead:
    item = service.get_schedule_item(item_id)
    check_item_access(item.user_id, current_user, "modify")
    return service.update_schedule_item(item_id, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_schedule_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    service: ScheduleService = Depends(get_schedule_service),
    db: Session = Depends(get_db),
) -> Response:
    item = service.get_schedule_item(item_id)
    check_item_access(item.user_id, current_user, "delete")
    service.delete_schedule_item(item_id)
    record_activity(db, f"Schedule item deleted: ID #{item_id}", source="schedule", user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

