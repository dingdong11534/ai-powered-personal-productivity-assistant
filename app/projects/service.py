"""
ProjectService — the layer app.interfaces routes call for projects.

Same role as app.tasks.service.TaskService: translates
ProjectCreate/ProjectUpdate into ORM objects, raises ProjectNotFoundError
for a missing id, and applies partial updates via
`model_dump(exclude_unset=True)`.

WHY ARCHIVING IS ITS OWN METHOD, NOT PART OF update_project
------------------------------------------------------------------
`archive_project` sets `archived_at = now()` and nothing else. It's kept
separate from `update_project` (rather than letting a client PUT
`{"archived_at": ...}`) for two reasons: `ProjectUpdate` doesn't even
expose `archived_at` as a field (see that schema's docstring), and
archiving is idempotent-by-design here — calling it twice just
re-stamps `archived_at` to a new "now", not an error, since "archive an
already-archived project" isn't a meaningful failure a caller needs to
handle.

HOW TO TEST
------------
See tests/test_project_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.projects.exceptions import ProjectNotFoundError
from app.projects.repository import ProjectRepository
from app.projects.schemas import ProjectCreate, ProjectUpdate
from app.storage.models import Project


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.repository = ProjectRepository(db)

    def create_project(self, data: ProjectCreate) -> Project:
        project = Project(**data.model_dump())
        return self.repository.create(project)

    def get_project(self, project_id: int) -> Project:
        project = self.repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def list_projects(
        self, *, skip: int = 0, limit: int = 100, include_archived: bool = True
    ) -> list[Project]:
        return self.repository.list(skip=skip, limit=limit, include_archived=include_archived)

    def update_project(self, project_id: int, data: ProjectUpdate) -> Project:
        project = self.get_project(project_id)
        changes = data.model_dump(exclude_unset=True)
        return self.repository.update(project, changes)

    def archive_project(self, project_id: int) -> Project:
        """Mark a project archived. Tasks referencing it are untouched —
        see app.tasks.service for what changes for those tasks (nothing,
        except they can no longer be *newly assigned* to this project).

        Uses a naive UTC timestamp (`datetime.now(timezone.utc)` with the
        tzinfo stripped) to match `created_at`/`updated_at`, which SQLite
        stores as naive text via `func.now()`. Keeping all timestamps in
        this project naive-but-UTC avoids comparing an aware and a naive
        datetime later, which raises `TypeError` in Python.
        """
        project = self.get_project(project_id)
        archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.repository.update(project, {"archived_at": archived_at})

    def unarchive_project(self, project_id: int) -> Project:
        """Remove the archived_at timestamp, restoring the project to active."""
        project = self.get_project(project_id)
        return self.repository.update(project, {"archived_at": None})

    def delete_project(self, project_id: int) -> None:
        """Delete a project by id. Tasks referencing this project are untouched;
        their project_id becomes NULL via ondelete='SET NULL' in the database model.
        """
        project = self.get_project(project_id)
        self.repository.delete(project)
