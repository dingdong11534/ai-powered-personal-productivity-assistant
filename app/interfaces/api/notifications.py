"""
Notification API routes. Same thin-route discipline as every other router.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import check_item_access, get_current_user
from app.notifications.schemas import NotificationCreate, NotificationRead
from app.notifications.service import NotificationService
from app.storage.database import get_db
from app.storage.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(
    data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationRead:
    return service.create_notification(data, user_id=current_user.id)


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    unread_only: bool = Query(default=False),
    search: str | None = Query(default=None),
    all_users: bool = Query(default=False, description="Admin only: list notifications across all users."),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    return service.list_notifications(
        skip=skip,
        limit=limit,
        unread_only=unread_only,
        search=search,
        user_id=target_user_id,
    )


@router.post("/read-all", response_model=dict[str, Any])
def mark_all_read(
    all_users: bool = Query(default=False, description="Admin only: mark all read across all users."),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> dict[str, Any]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    count = service.mark_all_read(user_id=target_user_id)
    return {"status": "ok", "marked_read": count}


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationRead:
    notif = service.get_notification(notification_id)
    check_item_access(notif.user_id, current_user, "view")
    return notif


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationRead:
    notif = service.get_notification(notification_id)
    check_item_access(notif.user_id, current_user, "modify")
    return service.mark_read(notification_id)


@router.post("/{notification_id}/unread", response_model=NotificationRead)
def mark_unread(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationRead:
    notif = service.get_notification(notification_id)
    check_item_access(notif.user_id, current_user, "modify")
    return service.mark_unread(notification_id)

