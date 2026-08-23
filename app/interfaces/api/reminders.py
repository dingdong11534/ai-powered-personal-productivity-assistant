"""
Reminder API routes.

`GET /reminders` accepts `?due=true` or `?upcoming=true` rather than
adding separate top-level routes for those two queries, keeping to the
brief's suggested route shape (`/reminders`, `/reminders/{id}`) while
still exposing "identify due reminders" / "list upcoming reminders" as
distinct, explicit query behaviors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.reminders.schemas import ReminderCreate, ReminderRead, ReminderUpdate
from app.reminders.service import ReminderService
from app.storage.database import get_db

router = APIRouter(prefix="/reminders", tags=["reminders"])


def get_reminder_service(db: Session = Depends(get_db)) -> ReminderService:
    return ReminderService(db)


@router.post("", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
def create_reminder(
    data: ReminderCreate, service: ReminderService = Depends(get_reminder_service)
) -> ReminderRead:
    return service.create_reminder(data)


@router.get("", response_model=list[ReminderRead])
def list_reminders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    due: bool = Query(default=False, description="Only not-yet-fired reminders whose time has passed."),
    upcoming: bool = Query(default=False, description="Only not-yet-fired reminders still ahead."),
    service: ReminderService = Depends(get_reminder_service),
) -> list[ReminderRead]:
    if due:
        return service.list_due_reminders()
    if upcoming:
        return service.list_upcoming_reminders()
    return service.list_reminders(skip=skip, limit=limit)


@router.get("/{reminder_id}", response_model=ReminderRead)
def get_reminder(
    reminder_id: int, service: ReminderService = Depends(get_reminder_service)
) -> ReminderRead:
    return service.get_reminder(reminder_id)


@router.put("/{reminder_id}", response_model=ReminderRead)
def update_reminder(
    reminder_id: int,
    data: ReminderUpdate,
    service: ReminderService = Depends(get_reminder_service),
) -> ReminderRead:
    return service.update_reminder(reminder_id, data)


@router.post("/{reminder_id}/fire", response_model=ReminderRead)
def fire_reminder(
    reminder_id: int, service: ReminderService = Depends(get_reminder_service)
) -> ReminderRead:
    return service.mark_fired(reminder_id)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(
    reminder_id: int, service: ReminderService = Depends(get_reminder_service)
) -> None:
    service.delete_reminder(reminder_id)
