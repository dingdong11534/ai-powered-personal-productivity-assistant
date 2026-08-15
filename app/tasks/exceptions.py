"""
Task domain exceptions.

WHY THESE EXIST SEPARATELY FROM HTTPException
--------------------------------------------------
`TaskNotFoundError` is a plain Python exception, not a FastAPI
`HTTPException`. app.tasks has no dependency on FastAPI at all (see the
package docstring) — raising `HTTPException` from the service layer would
mean importing a web-framework class into code that's supposed to be
usable from a future CLI or from voice, neither of which has an HTTP
response to return.

Instead, app.interfaces registers an exception handler (see
app/interfaces/main.py) that catches `TaskNotFoundError` and converts it
to a 404 response. That translation happens at the one place that
actually knows about HTTP — the boundary — not scattered through
business logic.
"""

from __future__ import annotations


class TaskNotFoundError(Exception):
    """Raised when a task lookup by id finds nothing."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")
