"""
Pomodoro API routes. Same thin-route discipline as every other router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import check_item_access, get_current_user
from app.notifications.service import record_activity
from app.pomodoro.schemas import PomodoroSessionCreate, PomodoroSessionEnd, PomodoroSessionRead
from app.pomodoro.service import PomodoroSessionService
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter(prefix="/pomodoro", tags=["pomodoro"])


def get_pomodoro_service(db: Session = Depends(get_db)) -> PomodoroSessionService:
    return PomodoroSessionService(db)


@router.post("", response_model=PomodoroSessionRead, status_code=status.HTTP_201_CREATED)
def start_session(
    data: PomodoroSessionCreate = PomodoroSessionCreate(),
    current_user: User = Depends(get_current_user),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
    db: Session = Depends(get_db),
) -> PomodoroSessionRead:
    session = service.start_session(task_id=data.task_id, session_name=data.session_name, user_id=current_user.id)
    title = data.session_name or "Focus session"
    record_activity(db, f"Pomodoro started: {title}", source="pomodoro", user_id=current_user.id)
    return session


@router.get("", response_model=list[PomodoroSessionRead])
def list_sessions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    task_id: int | None = Query(default=None),
    all_users: bool = Query(default=False, description="Admin only: list pomodoro sessions across all users."),
    current_user: User = Depends(get_current_user),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
) -> list[PomodoroSessionRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    return service.list_sessions(skip=skip, limit=limit, task_id=task_id, user_id=target_user_id)


@router.get("/{session_id}", response_model=PomodoroSessionRead)
def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
) -> PomodoroSessionRead:
    session = service.get_session(session_id)
    check_item_access(session.user_id, current_user, "view")
    return session


@router.post("/{session_id}/end", response_model=PomodoroSessionRead)
def end_session(
    session_id: int,
    data: PomodoroSessionEnd = PomodoroSessionEnd(),
    current_user: User = Depends(get_current_user),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
    db: Session = Depends(get_db),
) -> PomodoroSessionRead:
    session = service.get_session(session_id)
    check_item_access(session.user_id, current_user, "end")
    session = service.end_session(session_id, interrupted=data.interrupted)
    suffix = " (interrupted)" if data.interrupted else " (completed)"
    record_activity(db, f"Pomodoro ended: session #{session_id}{suffix}", source="pomodoro", user_id=current_user.id)
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    service: PomodoroSessionService = Depends(get_pomodoro_service),
) -> Response:
    session = service.get_session(session_id)
    check_item_access(session.user_id, current_user, "delete")
    service.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

