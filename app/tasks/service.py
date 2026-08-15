"""
TaskService — the layer app.interfaces routes actually call.

WHAT THIS DOES
---------------
Wraps TaskRepository with the behavior a caller actually wants: "fetch
this task, and if it doesn't exist, raise a meaningful error" rather than
"fetch this task, or None, good luck". Converts incoming Pydantic schemas
(TaskCreate/TaskUpdate) into the SQLAlchemy Task objects the repository
deals in.

WHY THIS LAYER EXISTS (given TaskRepository already exists)
-----------------------------------------------------------------
Routes (app/interfaces/api/tasks.py) call TaskService methods, never
TaskRepository directly. That's what keeps FastAPI-specific concerns
(HTTP status codes, request/response schemas) out of the persistence
code, and keeps business rules in exactly one place instead of duplicated
across every interface that will eventually create/modify tasks — the
same TaskService method a route calls today is what a future AI tool
call or CLI command would call too, without re-implementing "raise if
missing" or "only apply the fields that were actually sent" themselves.

Right now the business logic here is thin (not-found handling, partial
update semantics) because Task has no rules yet beyond "it exists or it
doesn't". This is exactly where Phase 1 features that do have rules —
task-dependency cycle checks, recurring-task generation — get added
later, without changing anything in app.interfaces or app.tasks.repository.

HOW TO TEST
------------
See tests/test_task_service.py. Because TaskService only depends on a
Session (via its constructor) and TaskRepository, tests build it directly
against the in-memory `db_session` fixture — no FastAPI, no HTTP,
no TestClient — which is what makes these the fastest, most direct tests
of the actual business rule ("missing id raises TaskNotFoundError").
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import Task
from app.tasks.exceptions import TaskNotFoundError
from app.tasks.repository import TaskRepository
from app.tasks.schemas import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, db: Session) -> None:
        self.repository = TaskRepository(db)

    def create_task(self, data: TaskCreate) -> Task:
        task = Task(**data.model_dump())
        return self.repository.create(task)

    def get_task(self, task_id: int) -> Task:
        """Fetch a task by id, or raise TaskNotFoundError."""
        task = self.repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(self, *, skip: int = 0, limit: int = 100) -> list[Task]:
        return self.repository.list(skip=skip, limit=limit)

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
        """
        task = self.get_task(task_id)
        changes = data.model_dump(exclude_unset=True)
        return self.repository.update(task, changes)

    def delete_task(self, task_id: int) -> None:
        """Delete a task by id, or raise TaskNotFoundError if it doesn't exist."""
        task = self.get_task(task_id)
        self.repository.delete(task)
