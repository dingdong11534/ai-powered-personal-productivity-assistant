"""
Project domain exceptions.

Plain Python exceptions, not `HTTPException` — same reasoning as
app.tasks.exceptions: app.projects has no dependency on FastAPI.
Translated to HTTP responses in app/interfaces/main.py.
"""

from __future__ import annotations


class ProjectNotFoundError(Exception):
    """Raised when a project lookup by id finds nothing."""

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        super().__init__(f"Project {project_id} not found")


class ArchivedProjectError(Exception):
    """Raised when an operation requires an active (non-archived) project.

    Currently raised by app.tasks.service when a task is created or
    updated to reference an archived project: assigning *new* work to a
    project that's been archived would undercut the point of archiving
    it. Tasks already assigned to a project before it was archived are
    unaffected — they keep their project_id and remain fully accessible
    (see docs/architecture.md's "Task -> Project relationship" section).
    """

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        super().__init__(f"Project {project_id} is archived")
