"""FastAPI routes for user discovery and public profiles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.storage.database import get_db
from app.storage.models import User
from app.users.schemas import UserProfilePublic
from app.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserProfilePublic])
def list_users(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserProfilePublic]:
    """List all registered users with their unique ID and online status (preferences kept private)."""
    svc = UserService(session)
    users = svc.list_users()
    return [
        UserProfilePublic(
            id=u.id,
            username=u.username,
            role=u.role,
            is_online=u.is_online,
        )
        for u in users
    ]


@router.get("/{user_id}/profile", response_model=UserProfilePublic)
def get_user_profile(
    user_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfilePublic:
    """View public profile of user by unique ID (only ID, username, and online status)."""
    svc = UserService(session)
    u = svc.get_by_id(user_id)
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User #{user_id} not found"
        )
    return UserProfilePublic(
        id=u.id,
        username=u.username,
        role=u.role,
        is_online=u.is_online,
    )
