"""Tests for app.notifications.service.NotificationService.

Run with: pytest tests/test_notification_service.py -v
"""

import pytest

from app.notifications.exceptions import NotificationNotFoundError
from app.notifications.schemas import NotificationCreate
from app.notifications.service import NotificationService


def test_create_notification_persists_it(db_session):
    service = NotificationService(db_session)

    notification = service.create_notification(
        NotificationCreate(title="Reminder fired", body="Call the dentist", source="reminder")
    )

    assert notification.id is not None
    assert notification.title == "Reminder fired"
    assert notification.read_at is None


def test_get_notification_raises_not_found_for_missing_id(db_session):
    service = NotificationService(db_session)

    with pytest.raises(NotificationNotFoundError):
        service.get_notification(999)


def test_list_notifications_unread_only(db_session):
    service = NotificationService(db_session)
    unread = service.create_notification(NotificationCreate(title="Unread"))
    read = service.create_notification(NotificationCreate(title="Will be read"))
    service.mark_read(read.id)

    notifications = service.list_notifications(unread_only=True)

    assert [n.id for n in notifications] == [unread.id]


def test_mark_read_sets_read_at(db_session):
    service = NotificationService(db_session)
    notification = service.create_notification(NotificationCreate(title="x"))

    read = service.mark_read(notification.id)

    assert read.read_at is not None


def test_mark_read_twice_is_idempotent(db_session):
    service = NotificationService(db_session)
    notification = service.create_notification(NotificationCreate(title="x"))
    first = service.mark_read(notification.id)

    second = service.mark_read(notification.id)

    assert second.read_at == first.read_at


def test_mark_unread_clears_read_at(db_session):
    service = NotificationService(db_session)
    notification = service.create_notification(NotificationCreate(title="x"))
    service.mark_read(notification.id)

    unread = service.mark_unread(notification.id)

    assert unread.read_at is None


def test_mark_unread_when_already_unread_is_idempotent(db_session):
    service = NotificationService(db_session)
    notification = service.create_notification(NotificationCreate(title="x"))

    result = service.mark_unread(notification.id)  # already unread — should not raise

    assert result.read_at is None
