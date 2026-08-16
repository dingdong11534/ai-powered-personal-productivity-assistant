"""
TaskDependencyService — the layer app.interfaces routes call for
dependencies, and the layer TaskService calls to check whether a task is
blocked from completion.

WHAT THIS DOES
---------------
Validates a dependency edge before it's ever written:
1. Rejects self-dependencies (`task_id == depends_on_task_id`).
2. Confirms both tasks exist (`TaskNotFoundError` otherwise).
3. Rejects an edge that already exists (`DuplicateDependencyError`) —
   checked explicitly rather than relying on the DB's composite primary
   key to reject a duplicate insert via `IntegrityError`, for the same
   "clear domain error over a raw DB error" reason as TagService.
4. Rejects an edge that would create a cycle (`DependencyCycleError`).

WHY CYCLE DETECTION LIVES HERE, IN THE SERVICE LAYER
----------------------------------------------------------
Per the brief's explicit instruction: "keep dependency logic in the task
service/domain layer, not in FastAPI routes." SQL has no clean way to
express "adding this edge must not create a cycle" as a table constraint
(that would need a recursive check across arbitrarily many rows at
insert time), so the graph traversal happens in Python, over data
fetched through TaskDependencyRepository.

THE ALGORITHM
---------------
`_would_create_cycle(task_id, depends_on_task_id)` does a breadth-first
search starting at `depends_on_task_id`, following existing dependency
edges outward (from any task, to the tasks *it* depends on). If that
search reaches `task_id`, it means `depends_on_task_id` already
(directly or transitively) depends on `task_id` — so adding
`task_id -> depends_on_task_id` would close the loop
`task_id -> depends_on_task_id -> ... -> task_id`. If the search
exhausts every reachable task without finding `task_id`, the new edge is
safe.

This runs in Python rather than as a single recursive SQL query
(SQLite supports `WITH RECURSIVE`, which could do this in one round
trip) because the dependency graph size here is small (one user's
tasks) and a plain BFS is far easier to read, test, and verify than a
recursive CTE — the performance difference is not worth the loss of
clarity at this scale. Revisit if the graph ever gets large enough for
that trade-off to flip.

HOW TO TEST
------------
See tests/test_dependency_service.py — including direct tests of the
self-dependency and multi-hop cycle cases (A->B->C, then reject C->A).
"""

from __future__ import annotations

from collections import deque

from sqlalchemy.orm import Session

from app.storage.models import Task, TaskDependency
from app.tasks.dependency_repository import TaskDependencyRepository
from app.tasks.exceptions import (
    DependencyCycleError,
    DuplicateDependencyError,
    SelfDependencyError,
    TaskNotFoundError,
)
from app.tasks.repository import TaskRepository


class TaskDependencyService:
    def __init__(self, db: Session) -> None:
        self.repository = TaskDependencyRepository(db)
        self.tasks = TaskRepository(db)

    def add_dependency(self, task_id: int, depends_on_task_id: int) -> TaskDependency:
        if task_id == depends_on_task_id:
            raise SelfDependencyError(task_id)

        self._require_task_exists(task_id)
        self._require_task_exists(depends_on_task_id)

        if self.repository.exists(task_id, depends_on_task_id):
            raise DuplicateDependencyError(task_id, depends_on_task_id)

        if self._would_create_cycle(task_id, depends_on_task_id):
            raise DependencyCycleError(task_id, depends_on_task_id)

        return self.repository.create(task_id, depends_on_task_id)

    def remove_dependency(self, task_id: int, depends_on_task_id: int) -> None:
        self._require_task_exists(task_id)
        self._require_task_exists(depends_on_task_id)
        self.repository.delete(task_id, depends_on_task_id)

    def list_dependencies(self, task_id: int) -> list[int]:
        """Return the ids of tasks `task_id` directly depends on."""
        self._require_task_exists(task_id)
        return self.repository.get_direct_dependencies(task_id)

    def get_unresolved_dependencies(self, task_id: int) -> list[Task]:
        """Tasks `task_id` depends on that aren't DONE yet. Used by
        TaskService to decide whether a task may be marked done."""
        return self.repository.get_unresolved_dependencies(task_id)

    def _require_task_exists(self, task_id: int) -> None:
        if self.tasks.get(task_id) is None:
            raise TaskNotFoundError(task_id)

    def _would_create_cycle(self, task_id: int, depends_on_task_id: int) -> bool:
        visited: set[int] = set()
        queue: deque[int] = deque([depends_on_task_id])
        while queue:
            current = queue.popleft()
            if current == task_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self.repository.get_direct_dependencies(current))
        return False
