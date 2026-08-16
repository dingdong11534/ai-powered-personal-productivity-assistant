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


class TagNotFoundError(Exception):
    """Raised when a tag lookup by id finds nothing."""

    def __init__(self, tag_id: int) -> None:
        self.tag_id = tag_id
        super().__init__(f"Tag {tag_id} not found")


class DuplicateTagError(Exception):
    """Raised when creating a tag whose name already exists.

    Tag names are unique (both by a DB `UNIQUE` constraint on
    `tags.name` and by this check in TagService.create_tag, which runs
    first so the caller gets a clear domain error instead of a raw
    `IntegrityError`). Attaching an *existing* tag to a task twice is
    handled differently — see TagService.attach_tag_to_task, which is
    idempotent rather than raising.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Tag {name!r} already exists")


class SelfDependencyError(Exception):
    """Raised when a task is made to depend on itself."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} cannot depend on itself")


class DependencyCycleError(Exception):
    """Raised when adding a dependency would create a cycle
    (A depends on B depends on ... depends on A)."""

    def __init__(self, task_id: int, depends_on_task_id: int) -> None:
        self.task_id = task_id
        self.depends_on_task_id = depends_on_task_id
        super().__init__(
            f"Task {task_id} cannot depend on task {depends_on_task_id}: "
            "would create a dependency cycle"
        )


class DuplicateDependencyError(Exception):
    """Raised when the exact same dependency edge is added twice."""

    def __init__(self, task_id: int, depends_on_task_id: int) -> None:
        self.task_id = task_id
        self.depends_on_task_id = depends_on_task_id
        super().__init__(
            f"Task {task_id} already depends on task {depends_on_task_id}"
        )


class UnresolvedDependencyError(Exception):
    """Raised when a task is marked done while a dependency isn't."""

    def __init__(self, task_id: int, unresolved_task_ids: list[int]) -> None:
        self.task_id = task_id
        self.unresolved_task_ids = unresolved_task_ids
        super().__init__(
            f"Task {task_id} cannot be marked done: depends on unresolved "
            f"task(s) {unresolved_task_ids}"
        )
