"""Schedule domain exceptions. Plain Python exceptions — see
app.tasks.exceptions for why."""

from __future__ import annotations


class ScheduleItemNotFoundError(Exception):
    """Raised when a schedule item lookup by id finds nothing."""

    def __init__(self, item_id: int) -> None:
        self.item_id = item_id
        super().__init__(f"Schedule item {item_id} not found")


class InvalidTimeRangeError(Exception):
    """Raised when `ends_at` is not after `starts_at`. Invalid as
    written — no server-side state could ever make it valid, hence
    HTTP 400 rather than 409 (see app/interfaces/main.py)."""

    def __init__(self) -> None:
        super().__init__("ends_at must be after starts_at")
