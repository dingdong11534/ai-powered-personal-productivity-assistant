"""
TaskDependencyRepository — direct, ORM-level access to `task_dependencies`.

Same "dumb, no business rules" role as the other repositories. Cycle
detection, self-dependency rejection, and the "unresolved dependency
blocks completion" rule all live in
app.tasks.dependency_service.TaskDependencyService — this module only
reads and writes edges.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Task, TaskDependency, TaskStatus


class TaskDependencyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def exists(self, task_id: int, depends_on_task_id: int) -> bool:
        stmt = select(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.depends_on_task_id == depends_on_task_id,
        )
        return self.db.scalars(stmt).first() is not None

    def create(self, task_id: int, depends_on_task_id: int) -> TaskDependency:
        dependency = TaskDependency(task_id=task_id, depends_on_task_id=depends_on_task_id)
        self.db.add(dependency)
        self.db.commit()
        return dependency

    def delete(self, task_id: int, depends_on_task_id: int) -> None:
        stmt = select(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.depends_on_task_id == depends_on_task_id,
        )
        dependency = self.db.scalars(stmt).first()
        if dependency is not None:
            self.db.delete(dependency)
            self.db.commit()

    def get_direct_dependencies(self, task_id: int) -> list[int]:
        """Return the ids of tasks that `task_id` directly depends on
        (one hop, not transitive) — the building block both cycle
        detection and unresolved-dependency checking traverse from."""
        stmt = select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task_id)
        return list(self.db.scalars(stmt))

    def get_unresolved_dependencies(self, task_id: int) -> list[Task]:
        """Return the Task rows `task_id` directly depends on that are
        not yet `DONE` — used to block marking `task_id` done while any
        remain. Deliberately direct (one hop) dependencies only: if A
        depends on B depends on C, and C isn't done, B is blocked from
        completion by the direct check on B; A is separately blocked by
        its direct dependency on B (which can't be DONE while it's
        blocked) — so transitively-blocked completion is enforced
        without this query itself needing to walk the whole chain.
        """
        direct_ids = self.get_direct_dependencies(task_id)
        if not direct_ids:
            return []
        stmt = select(Task).where(Task.id.in_(direct_ids), Task.status != TaskStatus.DONE)
        return list(self.db.scalars(stmt))
