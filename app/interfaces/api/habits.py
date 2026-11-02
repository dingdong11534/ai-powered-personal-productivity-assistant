"""
Habit API routes.

Same thin-route discipline as every other router in this project: parse
input, call one HabitService method, return the result.

`/habits/{id}/statistics` isn't in the brief's suggested route list but
is added since streaks/statistics are explicit Phase 2 requirements that
need *some* way to be requested — kept as a GET, alongside
`/habits/{id}/history`, rather than folded into `HabitRead` on every
`GET /habits` call, since computing statistics is more work than reading
a row and most callers listing habits don't need it for every one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import check_item_access, get_current_user
from app.habits.schemas import (
    HabitCompletionCreate,
    HabitCompletionRead,
    HabitCreate,
    HabitRead,
    HabitStatisticsRead,
    HabitUpdate,
)
from app.habits.service import HabitService
from app.notifications.service import record_activity
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter(prefix="/habits", tags=["habits"])


def get_habit_service(db: Session = Depends(get_db)) -> HabitService:
    return HabitService(db)


@router.post("", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
def create_habit(
    data: HabitCreate,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
    db: Session = Depends(get_db),
) -> HabitRead:
    habit = service.create_habit(data, user_id=current_user.id)
    record_activity(db, f"Habit created: {habit.name}", source="habit", user_id=current_user.id)
    return habit


@router.get("", response_model=list[HabitRead])
def list_habits(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    include_archived: bool = Query(default=True),
    all_users: bool = Query(default=False, description="Admin only: list habits across all users."),
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> list[HabitRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    return service.list_habits(
        skip=skip,
        limit=limit,
        include_archived=include_archived,
        user_id=target_user_id,
    )


@router.get("/{habit_id}", response_model=HabitRead)
def get_habit(
    habit_id: int,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "view")
    return habit


@router.put("/{habit_id}", response_model=HabitRead)
def update_habit(
    habit_id: int,
    data: HabitUpdate,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "modify")
    return service.update_habit(habit_id, data)


@router.post("/{habit_id}/archive", response_model=HabitRead)
def archive_habit(
    habit_id: int,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "archive")
    return service.archive_habit(habit_id)


@router.post("/{habit_id}/unarchive", response_model=HabitRead)
def unarchive_habit(
    habit_id: int,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> HabitRead:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "unarchive")
    return service.unarchive_habit(habit_id)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_habit(
    habit_id: int,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
    db: Session = Depends(get_db),
) -> Response:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "delete")
    service.delete_habit(habit_id)
    record_activity(db, f"Habit deleted: ID #{habit_id}", source="habit", user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{habit_id}/complete",
    response_model=HabitCompletionRead,
    status_code=status.HTTP_201_CREATED,
)
def complete_habit(
    habit_id: int,
    data: HabitCompletionCreate = HabitCompletionCreate(),
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
    db: Session = Depends(get_db),
) -> HabitCompletionRead:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "complete")
    comp = service.record_completion(habit_id, completed_at=data.completed_at)
    record_activity(db, f"Habit completed: {habit.name}", source="habit", user_id=current_user.id)
    return comp


@router.get("/{habit_id}/history", response_model=list[HabitCompletionRead])
def get_habit_history(
    habit_id: int,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> list[HabitCompletionRead]:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "view")
    return service.get_completion_history(habit_id)


@router.get("/{habit_id}/statistics", response_model=HabitStatisticsRead)
def get_habit_statistics(
    habit_id: int,
    current_user: User = Depends(get_current_user),
    service: HabitService = Depends(get_habit_service),
) -> HabitStatisticsRead:
    habit = service.get_habit(habit_id)
    check_item_access(habit.user_id, current_user, "view")
    return service.get_statistics(habit_id)

