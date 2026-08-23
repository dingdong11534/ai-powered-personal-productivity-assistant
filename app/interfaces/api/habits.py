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

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.habits.schemas import (
    HabitCompletionCreate,
    HabitCompletionRead,
    HabitCreate,
    HabitRead,
    HabitStatisticsRead,
    HabitUpdate,
)
from app.habits.service import HabitService
from app.storage.database import get_db

router = APIRouter(prefix="/habits", tags=["habits"])


def get_habit_service(db: Session = Depends(get_db)) -> HabitService:
    return HabitService(db)


@router.post("", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
def create_habit(data: HabitCreate, service: HabitService = Depends(get_habit_service)) -> HabitRead:
    return service.create_habit(data)


@router.get("", response_model=list[HabitRead])
def list_habits(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    include_archived: bool = Query(default=True),
    service: HabitService = Depends(get_habit_service),
) -> list[HabitRead]:
    return service.list_habits(skip=skip, limit=limit, include_archived=include_archived)


@router.get("/{habit_id}", response_model=HabitRead)
def get_habit(habit_id: int, service: HabitService = Depends(get_habit_service)) -> HabitRead:
    return service.get_habit(habit_id)


@router.put("/{habit_id}", response_model=HabitRead)
def update_habit(
    habit_id: int, data: HabitUpdate, service: HabitService = Depends(get_habit_service)
) -> HabitRead:
    return service.update_habit(habit_id, data)


@router.post("/{habit_id}/archive", response_model=HabitRead)
def archive_habit(habit_id: int, service: HabitService = Depends(get_habit_service)) -> HabitRead:
    return service.archive_habit(habit_id)


@router.post(
    "/{habit_id}/complete",
    response_model=HabitCompletionRead,
    status_code=status.HTTP_201_CREATED,
)
def complete_habit(
    habit_id: int,
    data: HabitCompletionCreate = HabitCompletionCreate(),
    service: HabitService = Depends(get_habit_service),
) -> HabitCompletionRead:
    """Body is optional — `POST /habits/{id}/complete` with no body at
    all records a completion for right now, which is the common case;
    send `{"completed_at": ...}` only to log a past completion."""
    return service.record_completion(habit_id, completed_at=data.completed_at)


@router.get("/{habit_id}/history", response_model=list[HabitCompletionRead])
def get_habit_history(
    habit_id: int, service: HabitService = Depends(get_habit_service)
) -> list[HabitCompletionRead]:
    return service.get_completion_history(habit_id)


@router.get("/{habit_id}/statistics", response_model=HabitStatisticsRead)
def get_habit_statistics(
    habit_id: int, service: HabitService = Depends(get_habit_service)
) -> HabitStatisticsRead:
    return service.get_statistics(habit_id)
