"""
TaskService — the layer app.interfaces routes actually call.

WHAT THIS DOES
---------------
Wraps TaskRepository with the behavior a caller actually wants: "fetch
this task, and if it doesn't exist, raise a meaningful error" rather than
"fetch this task, or None, good luck". Converts incoming Pydantic schemas
(TaskCreate/TaskUpdate) into the SQLAlchemy Task objects the repository
deals in. As of Phase 1, also:

- validates `project_id` against ProjectRepository (must exist, must
  not be archived) whenever it's set on create or changed on update;
- blocks a task from being marked `done` while it has unresolved
  dependencies, via TaskDependencyRepository.

WHY THIS LAYER EXISTS (given TaskRepository already exists)
-----------------------------------------------------------------
Routes (app/interfaces/api/tasks.py) call TaskService methods, never
TaskRepository directly. That's what keeps FastAPI-specific concerns
out of the persistence code, and keeps business rules in exactly one
place instead of duplicated across every interface that will eventually
create/modify tasks.

WHY TaskService DEPENDS ON app.projects AND ON THE DEPENDENCY REPOSITORY
--------------------------------------------------------------------------
This is a deliberate exception to "domain packages don't depend on each
other" — see app/tasks/__init__.py and app/projects/__init__.py: a
task's validity is genuinely entangled with project state (can't attach
to an archived project) and with dependency state (can't complete with
open dependencies). Both rules belong conceptually to *Task* ("is this
task allowed to be in this state?"), not to Project or to the dependency
graph in isolation, which is why the checks live here. The coupling is
one-way: app.projects never imports from app.tasks.

HOW TO TEST
------------
See tests/test_task_service.py for the pre-existing CRUD/not-found
behavior, and tests/test_task_service_phase1.py for the Phase 1
additions (archived-project rejection, dependency-blocked completion) —
kept in a separate test file so each stays focused rather than growing
one large file test-by-test.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.projects.exceptions import ArchivedProjectError, ProjectNotFoundError
from app.projects.repository import ProjectRepository
from app.storage.models import Task, TaskStatus
from app.tasks.dependency_repository import TaskDependencyRepository
from app.tasks.exceptions import TaskNotFoundError, UnresolvedDependencyError
from app.tasks.repository import TaskRepository
from app.tasks.schemas import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, db: Session) -> None:
        self.repository = TaskRepository(db)
        self.projects = ProjectRepository(db)
        self.dependencies = TaskDependencyRepository(db)

    def create_task(self, data: TaskCreate) -> Task:
        fields = data.model_dump()
        if fields.get("project_id") is not None:
            self._require_active_project(fields["project_id"])
        task = Task(**fields)
        return self.repository.create(task)

    def get_task(self, task_id: int) -> Task:
        """Fetch a task by id, or raise TaskNotFoundError."""
        task = self.repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        status: TaskStatus | None = None,
        priority: int | None = None,
        project_id: int | None = None,
        tag_id: int | None = None,
        deadline_before: datetime | None = None,
        deadline_after: datetime | None = None,
        completed: bool | None = None,
        search: str | None = None,
    ) -> list[Task]:
        """See TaskRepository.list for what each filter means; this
        method adds no business logic of its own on top — filtering
        doesn't touch project/dependency validation."""
        return self.repository.list(
            skip=skip,
            limit=limit,
            status=status,
            priority=priority,
            project_id=project_id,
            tag_id=tag_id,
            deadline_before=deadline_before,
            deadline_after=deadline_after,
            completed=completed,
            search=search,
        )

    def update_task(self, task_id: int, data: TaskUpdate) -> Task:
        """Apply only the fields the client actually sent (see
        TaskUpdate's docstring on partial-update semantics), or raise
        TaskNotFoundError if the task doesn't exist.

        `exclude_unset=True` is what makes this a *partial* update: a
        field the client never included in the request body is left
        untouched, distinct from a field explicitly sent as `null`
        (which — for a nullable field like `description` — *would* be
        applied, clearing it). That distinction is exactly what a client
        needs to be able to express "leave this alone" vs. "clear this".

        Two Phase 1 checks run before the update is applied:
        - if `project_id` is among the changed fields and non-null, the
          referenced project must exist and not be archived;
        - if `status` is being changed to `done`, the task must have no
          unresolved dependencies.
        """
        task = self.get_task(task_id)
        changes = data.model_dump(exclude_unset=True)

        if "project_id" in changes and changes["project_id"] is not None:
            self._require_active_project(changes["project_id"])

        if changes.get("status") == TaskStatus.DONE:
            self._require_no_unresolved_dependencies(task_id)

        return self.repository.update(task, changes)

    def delete_task(self, task_id: int) -> None:
        """Delete a task by id, or raise TaskNotFoundError if it doesn't exist.

        Deleting a task also removes its dependency edges and tag
        attachments — both `task_dependencies` and `task_tags` declare
        `ondelete="CASCADE"` on their foreign keys to `tasks.id` (see
        app.storage.models), so this is handled by the database itself,
        not by extra code here.
        """
        task = self.get_task(task_id)
        self.repository.delete(task)

    def _require_active_project(self, project_id: int) -> None:
        project = self.projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        if project.archived_at is not None:
            raise ArchivedProjectError(project_id)

    def _require_no_unresolved_dependencies(self, task_id: int) -> None:
        unresolved = self.dependencies.get_unresolved_dependencies(task_id)
        if unresolved:
            raise UnresolvedDependencyError(task_id, [t.id for t in unresolved])
