"""
Notification API routes. Same thin-route discipline as every other router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.notifications.schemas import NotificationCreate, NotificationRead
from app.notifications.service import NotificationService
from app.storage.database import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(
    data: NotificationCreate, service: NotificationService = Depends(get_notification_service)
) -> NotificationRead:
    return service.create_notification(data)


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    unread_only: bool = Query(default=False),
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationRead]:
    return service.list_notifications(skip=skip, limit=limit, unread_only=unread_only)


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(
    notification_id: int, service: NotificationService = Depends(get_notification_service)
) -> NotificationRead:
    return service.get_notification(notification_id)


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: int, service: NotificationService = Depends(get_notification_service)
) -> NotificationRead:
    return service.mark_read(notification_id)


@router.post("/{notification_id}/unread", response_model=NotificationRead)
def mark_unread(
    notification_id: int, service: NotificationService = Depends(get_notification_service)
) -> NotificationRead:
    return service.mark_unread(notification_id)
