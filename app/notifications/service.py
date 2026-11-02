"""
NotificationService — the layer app.interfaces calls for notifications.

Deliberately the thinnest service in this project: creation and
read/unread state have no business rules beyond "does it exist" — see
app.notifications's package docstring for why any real dispatch/delivery
logic is out of scope here.

`mark_read`/`mark_unread` are idempotent (setting `read_at` when it's
already set, or clearing it when it's already null, both just succeed)
— same reasoning as ReminderService.mark_fired: a client shouldn't have
to check current state before flipping it.

HOW TO TEST
------------
See tests/test_notification_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.notifications.exceptions import NotificationNotFoundError
from app.notifications.repository import NotificationRepository
from app.notifications.schemas import NotificationCreate
from app.storage.models import Notification


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.repository = NotificationRepository(db)

    def create_notification(self, data: NotificationCreate, *, user_id: int | None = None) -> Notification:
        fields = data.model_dump()
        if user_id is not None:
            fields["user_id"] = user_id
        notification = Notification(**fields)
        return self.repository.create(notification)

    def get_notification(self, notification_id: int) -> Notification:
        notification = self.repository.get(notification_id)
        if notification is None:
            raise NotificationNotFoundError(notification_id)
        return notification

    def list_notifications(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        unread_only: bool = False,
        search: str | None = None,
        user_id: int | None = None,
    ) -> list[Notification]:
        return self.repository.list(
            skip=skip,
            limit=limit,
            unread_only=unread_only,
            search=search,
            user_id=user_id,
        )

    def mark_read(self, notification_id: int) -> Notification:
        notification = self.get_notification(notification_id)
        if notification.read_at is not None:
            return notification  # idempotent
        read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.update(notification, {"read_at": read_at})

    def mark_unread(self, notification_id: int) -> Notification:
        notification = self.get_notification(notification_id)
        if notification.read_at is None:
            return notification  # idempotent
        return self.repository.update(notification, {"read_at": None})

    def mark_all_read(self, *, user_id: int | None = None) -> int:
        """Mark all unread notifications as read."""
        unread = self.repository.list(unread_only=True, limit=500, user_id=user_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        count = 0
        for n in unread:
            self.repository.update(n, {"read_at": now})
            count += 1
        return count


def record_activity(
    db: Session,
    title: str,
    body: str | None = None,
    source: str | None = None,
    user_id: int | None = None,
) -> Notification | None:
    """Helper to record user/system/assistant activity into the notifications feed and user activity files."""
    try:
        svc = NotificationService(db)
        notif = svc.create_notification(
            NotificationCreate(title=title, body=body, source=source),
            user_id=user_id,
        )

        # File-based organized storage per user
        try:
            from datetime import datetime, timezone
            from app.core.config import get_settings

            ws_dir = get_settings().ensure_workspace_dir()
            users_dir = ws_dir / "users"
            now_iso = datetime.now(timezone.utc).isoformat()
            log_line = f"[{now_iso}] [{source or 'general'}] {title}" + (f" - {body}" if body else "") + "\n"

            if user_id:
                u_dir = users_dir / f"user_{user_id}"
                u_dir.mkdir(parents=True, exist_ok=True)
                with (u_dir / "activity.log").open("a", encoding="utf-8") as f:
                    f.write(log_line)
            else:
                users_dir.mkdir(parents=True, exist_ok=True)
                with (users_dir / "system_activity.log").open("a", encoding="utf-8") as f:
                    f.write(log_line)
        except Exception:
            pass

        return notif
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Could not record activity notification: %s", exc)
        return None
