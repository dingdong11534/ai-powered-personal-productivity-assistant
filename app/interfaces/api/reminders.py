"""
Reminder API routes.

`GET /reminders` accepts `?due=true` or `?upcoming=true` rather than
adding separate top-level routes for those two queries, keeping to the
brief's suggested route shape (`/reminders`, `/reminders/{id}`) while
still exposing "identify due reminders" / "list upcoming reminders" as
distinct, explicit query behaviors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import check_item_access, get_current_user
from app.notifications.service import record_activity
from app.reminders.schemas import ReminderCreate, ReminderRead, ReminderUpdate
from app.reminders.service import ReminderService
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter(prefix="/reminders", tags=["reminders"])


def get_reminder_service(db: Session = Depends(get_db)) -> ReminderService:
    return ReminderService(db)


@router.post("", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
def create_reminder(
    data: ReminderCreate,
    current_user: User = Depends(get_current_user),
    service: ReminderService = Depends(get_reminder_service),
    db: Session = Depends(get_db),
) -> ReminderRead:
    rem = service.create_reminder(data, user_id=current_user.id)
    record_activity(db, f"Reminder set: {rem.message}", source="reminder", user_id=current_user.id)
    return rem


@router.get("", response_model=list[ReminderRead])
def list_reminders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    due: bool = Query(default=False, description="Only not-yet-fired reminders whose time has passed."),
    upcoming: bool = Query(default=False, description="Only not-yet-fired reminders still ahead."),
    all_users: bool = Query(default=False, description="Admin only: list reminders across all users."),
    current_user: User = Depends(get_current_user),
    service: ReminderService = Depends(get_reminder_service),
) -> list[ReminderRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    if due:
        return service.list_due_reminders(user_id=target_user_id)
    if upcoming:
        return service.list_upcoming_reminders(user_id=target_user_id)
    return service.list_reminders(skip=skip, limit=limit, user_id=target_user_id)


@router.get("/{reminder_id}", response_model=ReminderRead)
def get_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    service: ReminderService = Depends(get_reminder_service),
) -> ReminderRead:
    rem = service.get_reminder(reminder_id)
    check_item_access(rem.user_id, current_user, "view")
    return rem


@router.put("/{reminder_id}", response_model=ReminderRead)
def update_reminder(
    reminder_id: int,
    data: ReminderUpdate,
    current_user: User = Depends(get_current_user),
    service: ReminderService = Depends(get_reminder_service),
) -> ReminderRead:
    rem = service.get_reminder(reminder_id)
    check_item_access(rem.user_id, current_user, "modify")
    return service.update_reminder(reminder_id, data)


@router.post("/{reminder_id}/fire", response_model=ReminderRead)
def fire_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    service: ReminderService = Depends(get_reminder_service),
    db: Session = Depends(get_db),
) -> ReminderRead:
    rem = service.get_reminder(reminder_id)
    check_item_access(rem.user_id, current_user, "fire")
    rem = service.mark_fired(reminder_id)
    record_activity(db, f"Reminder fired: {rem.message}", source="reminder", user_id=current_user.id)
    return rem


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user),
    service: ReminderService = Depends(get_reminder_service),
    db: Session = Depends(get_db),
) -> Response:
    rem = service.get_reminder(reminder_id)
    check_item_access(rem.user_id, current_user, "delete")
    service.delete_reminder(reminder_id)
    record_activity(db, f"Reminder deleted: ID #{reminder_id}", source="reminder", user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

