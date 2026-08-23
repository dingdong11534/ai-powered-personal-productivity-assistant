"""
Notification domain logic.

exceptions.py  - NotificationNotFoundError.
schemas.py     - Pydantic schemas: create/read.
repository.py  - NotificationRepository: direct CRUD + unread query.
service.py     - NotificationService: create, list (all/unread), mark
                  read/unread.

WHY OS-LEVEL DESKTOP NOTIFICATIONS ARE NOT HERE
------------------------------------------------------
This package only manages `Notification` *records* — title, body,
read/unread state. It has no dependency on any OS-specific notification
API (Linux `notify-send`/D-Bus, Windows toast notifications, macOS
`NSUserNotification`, etc.), and none is added in this phase — see the
Phase 2 brief's explicit "do not implement actual desktop notifications
yet". When that's built, it belongs in `app.integrations` (an adapter
that *reads* Notification records and dispatches them to the OS), kept
separate from this package specifically so the core domain (what a
notification *is*) never depends on which operating system the app
happens to be running on. This package is the seam that future adapter
will plug into.
"""
