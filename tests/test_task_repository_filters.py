"""Tests for the filtering/search additions to
app.tasks.repository.TaskRepository.list().

Run with: pytest tests/test_task_repository_filters.py -v
"""

from datetime import datetime

from app.storage.models import Project, Tag, Task, TaskStatus, task_tags
from app.tasks.repository import TaskRepository


def test_filter_by_status(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Todo task", status=TaskStatus.TODO))
    repo.create(Task(title="Done task", status=TaskStatus.DONE))

    results = repo.list(status=TaskStatus.DONE)

    assert [t.title for t in results] == ["Done task"]


def test_filter_by_priority(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Critical", priority=1))
    repo.create(Task(title="Low", priority=4))

    results = repo.list(priority=1)

    assert [t.title for t in results] == ["Critical"]


def test_filter_by_project_id(db_session):
    db_session.add(Project(name="P1"))
    db_session.commit()
    project = db_session.query(Project).first()
    repo = TaskRepository(db_session)
    repo.create(Task(title="In project", project_id=project.id))
    repo.create(Task(title="No project"))

    results = repo.list(project_id=project.id)

    assert [t.title for t in results] == ["In project"]


def test_filter_by_deadline_range(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Early", deadline=datetime(2026, 1, 1)))
    repo.create(Task(title="Late", deadline=datetime(2026, 6, 1)))

    results = repo.list(deadline_before=datetime(2026, 3, 1))
    assert [t.title for t in results] == ["Early"]

    results = repo.list(deadline_after=datetime(2026, 3, 1))
    assert [t.title for t in results] == ["Late"]


def test_filter_by_completed_true(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Todo", status=TaskStatus.TODO))
    repo.create(Task(title="Done", status=TaskStatus.DONE))

    results = repo.list(completed=True)

    assert [t.title for t in results] == ["Done"]


def test_filter_by_completed_false(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Todo", status=TaskStatus.TODO))
    repo.create(Task(title="Done", status=TaskStatus.DONE))

    results = repo.list(completed=False)

    assert [t.title for t in results] == ["Todo"]


def test_search_matches_title(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Buy groceries"))
    repo.create(Task(title="Clean house"))

    results = repo.list(search="groceries")

    assert [t.title for t in results] == ["Buy groceries"]


def test_search_matches_description(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Task A", description="Remember the milk"))
    repo.create(Task(title="Task B", description="Unrelated"))

    results = repo.list(search="milk")

    assert [t.title for t in results] == ["Task A"]


def test_search_is_case_insensitive(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Buy GROCERIES"))

    results = repo.list(search="groceries")

    assert len(results) == 1


def test_filter_by_tag_id(db_session):
    tag = Tag(name="urgent")
    db_session.add(tag)
    db_session.commit()
    repo = TaskRepository(db_session)
    tagged = repo.create(Task(title="Tagged"))
    repo.create(Task(title="Untagged"))
    db_session.execute(task_tags.insert().values(task_id=tagged.id, tag_id=tag.id))
    db_session.commit()

    results = repo.list(tag_id=tag.id)

    assert [t.title for t in results] == ["Tagged"]


def test_filters_combine_with_and(db_session):
    repo = TaskRepository(db_session)
    repo.create(Task(title="Match", priority=1, status=TaskStatus.TODO))
    repo.create(Task(title="Wrong priority", priority=4, status=TaskStatus.TODO))
    repo.create(Task(title="Wrong status", priority=1, status=TaskStatus.DONE))

    results = repo.list(priority=1, status=TaskStatus.TODO)

    assert [t.title for t in results] == ["Match"]
