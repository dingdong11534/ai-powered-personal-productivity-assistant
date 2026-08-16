"""Tests for the priority system: labels, DB-level constraint (defense in
depth behind the Pydantic `ge=1, le=4` validation already covered by
tests/test_tasks_api.py's test_create_task_rejects_priority_out_of_range),
and sort ordering.

Run with: pytest tests/test_priority.py -v
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.storage.models import PRIORITY_LABELS, Task
from app.tasks.repository import TaskRepository


def test_priority_labels_cover_the_full_1_to_4_range():
    assert PRIORITY_LABELS == {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}


def test_priority_below_range_is_rejected_at_the_database_level(db_session):
    """A second line of defense behind the Pydantic schema's ge=1: even
    a caller that bypasses the API (e.g. a future AI tool call
    constructing a Task directly) can't write an invalid priority."""
    repo = TaskRepository(db_session)

    with pytest.raises(IntegrityError):
        repo.create(Task(title="Bad priority", priority=0))


def test_priority_above_range_is_rejected_at_the_database_level(db_session):
    repo = TaskRepository(db_session)

    with pytest.raises(IntegrityError):
        repo.create(Task(title="Bad priority", priority=5))


def test_listing_by_priority_orders_most_urgent_first_when_sorted(db_session):
    """priority=1 (Critical) sorts before priority=4 (Low) as a plain
    integer comparison — verifies the "lower number = more urgent"
    meaning is actually usable for sorting, not just documentation."""
    repo = TaskRepository(db_session)
    repo.create(Task(title="Low priority", priority=4))
    repo.create(Task(title="Critical priority", priority=1))
    repo.create(Task(title="Medium priority", priority=3))

    all_tasks = repo.list()
    ordered_by_urgency = sorted(all_tasks, key=lambda t: t.priority)

    assert [t.title for t in ordered_by_urgency] == [
        "Critical priority",
        "Medium priority",
        "Low priority",
    ]
