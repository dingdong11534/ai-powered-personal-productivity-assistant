"""
Pomodoro API routes. Same thin-route discipline as every other router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.pomodoro.schemas import PomodoroSessionCreate, PomodoroSessionEnd, PomodoroSessionRead
from app.pomodoro.service import PomodoroSessionService
from app.storage.database import get_db

router = APIRouter(prefix="/pomodoro", tags=["pomodoro"])


def get_pomodoro_service(db: Session = Depends(get_db)) -> PomodoroSessionService:
    return PomodoroSessionService(db)


@router.post("", response_model=PomodoroSessionRead, status_code=status.HTTP_201_CREATED)
def start_session(
    data: PomodoroSessionCreate = PomodoroSessionCreate(),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
) -> PomodoroSessionRead:
    return service.start_session(task_id=data.task_id)


@router.get("", response_model=list[PomodoroSessionRead])
def list_sessions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    task_id: int | None = Query(default=None),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
) -> list[PomodoroSessionRead]:
    return service.list_sessions(skip=skip, limit=limit, task_id=task_id)


@router.get("/{session_id}", response_model=PomodoroSessionRead)
def get_session(
    session_id: int, service: PomodoroSessionService = Depends(get_pomodoro_service)
) -> PomodoroSessionRead:
    return service.get_session(session_id)


@router.post("/{session_id}/end", response_model=PomodoroSessionRead)
def end_session(
    session_id: int,
    data: PomodoroSessionEnd = PomodoroSessionEnd(),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
) -> PomodoroSessionRead:
    return service.end_session(session_id, interrupted=data.interrupted)
