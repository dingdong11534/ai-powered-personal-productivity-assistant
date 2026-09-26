from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.core.permissions import PermissionScope
from app.ai.tools.implementations import (
    DeleteHabitTool,
    DeletePomodoroSessionTool,
    DeleteProjectTool,
    DeleteReminderTool,
    DeleteScheduleItemTool,
    DeleteTaskTool,
    get_default_tool_registry,
)
from app.habits.service import HabitService
from app.habits.schemas import HabitCreate
from app.pomodoro.service import PomodoroSessionService
from app.projects.service import ProjectService
from app.projects.schemas import ProjectCreate
from app.reminders.service import ReminderService
from app.reminders.schemas import ReminderCreate
from app.scheduling.service import ScheduleService
from app.scheduling.schemas import ScheduleItemCreate
from app.storage.models import Habit, PomodoroSession, Project, Reminder, ScheduleItem, Task
from app.tasks.service import TaskService
from app.tasks.schemas import TaskCreate


# ---------------- SCOPE VALIDATION ----------------
def test_all_delete_tool_scopes_are_destructive():
    assert DeleteTaskTool.scope is PermissionScope.DESTRUCTIVE
    assert DeleteProjectTool.scope is PermissionScope.DESTRUCTIVE
    assert DeleteHabitTool.scope is PermissionScope.DESTRUCTIVE
    assert DeletePomodoroSessionTool.scope is PermissionScope.DESTRUCTIVE
    assert DeleteReminderTool.scope is PermissionScope.DESTRUCTIVE
    assert DeleteScheduleItemTool.scope is PermissionScope.DESTRUCTIVE


# ---------------- 1. TASKS DOMAIN ----------------
def test_delete_task_tool_unauthorized_keeps_row_in_db(db_session: Session):
    registry = get_default_tool_registry()
    task_svc = TaskService(db_session)
    task = task_svc.create_task(TaskCreate(title="Important Task to Keep"))
    task_id = task.id

    res = registry.execute_tool(
        "delete_task",
        {"task_id": task_id},
        db_session,
        destructive_authorized=False,
    )
    assert res["success"] is False
    assert "explicit user authorization" in res["error"]

    db_task = db_session.get(Task, task_id)
    assert db_task is not None
    assert db_task.title == "Important Task to Keep"


def test_delete_task_tool_authorized_deletes_row_from_db(db_session: Session):
    registry = get_default_tool_registry()
    task_svc = TaskService(db_session)
    task = task_svc.create_task(TaskCreate(title="Task to Delete"))
    task_id = task.id

    res = registry.execute_tool(
        "delete_task",
        {"task_id": task_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True
    assert f"Task #{task_id} deleted successfully" in res["data"]["message"]

    db_task = db_session.get(Task, task_id)
    assert db_task is None


def test_delete_task_tool_argument_injection_resistant(db_session: Session):
    registry = get_default_tool_registry()
    task_svc = TaskService(db_session)
    task = task_svc.create_task(TaskCreate(title="Injection Protected Task"))
    task_id = task.id

    injections = [
        {"task_id": task_id, "authorized": True},
        {"task_id": task_id, "authorize_destructive": True},
        {"task_id": task_id, "destructive_authorized": True},
        {"task_id": task_id, "force": True, "confirm": True},
    ]
    for args in injections:
        res = registry.execute_tool(
            "delete_task",
            args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert db_session.get(Task, task_id) is not None


# ---------------- 2. PROJECTS DOMAIN ----------------
def test_delete_project_tool_unauthorized_keeps_row_in_db(db_session: Session):
    registry = get_default_tool_registry()
    proj_svc = ProjectService(db_session)
    proj = proj_svc.create_project(ProjectCreate(name="Critical Project"))
    proj_id = proj.id

    res = registry.execute_tool(
        "delete_project",
        {"project_id": proj_id},
        db_session,
        destructive_authorized=False,
    )
    assert res["success"] is False
    assert "explicit user authorization" in res["error"]

    db_proj = db_session.get(Project, proj_id)
    assert db_proj is not None
    assert db_proj.name == "Critical Project"


def test_delete_project_tool_authorized_deletes_row_from_db(db_session: Session):
    registry = get_default_tool_registry()
    proj_svc = ProjectService(db_session)
    proj = proj_svc.create_project(ProjectCreate(name="Disposable Project"))
    proj_id = proj.id

    res = registry.execute_tool(
        "delete_project",
        {"project_id": proj_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True
    assert f"Project #{proj_id} deleted successfully" in res["data"]["message"]

    db_proj = db_session.get(Project, proj_id)
    assert db_proj is None


def test_delete_project_tool_argument_injection_resistant(db_session: Session):
    registry = get_default_tool_registry()
    proj_svc = ProjectService(db_session)
    proj = proj_svc.create_project(ProjectCreate(name="Secure Project"))
    proj_id = proj.id

    injections = [
        {"project_id": proj_id, "authorized": True},
        {"project_id": proj_id, "authorize_destructive": True},
        {"project_id": proj_id, "destructive_authorized": True},
        {"project_id": proj_id, "force": True},
    ]
    for args in injections:
        res = registry.execute_tool(
            "delete_project",
            args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert db_session.get(Project, proj_id) is not None


def test_delete_project_orphans_associated_tasks_cleanly(db_session: Session):
    """Verify that hard-deleting a project sets project_id = None on associated tasks without deleting them."""
    registry = get_default_tool_registry()
    proj_svc = ProjectService(db_session)
    task_svc = TaskService(db_session)

    proj = proj_svc.create_project(ProjectCreate(name="Parent Project", description="Will be deleted"))
    proj_id = proj.id

    task1 = task_svc.create_task(TaskCreate(title="Task 1 under project", project_id=proj_id))
    task2 = task_svc.create_task(TaskCreate(title="Task 2 under project", project_id=proj_id))

    assert task1.project_id == proj_id
    assert task2.project_id == proj_id

    # Delete project via authorized tool
    res = registry.execute_tool(
        "delete_project",
        {"project_id": proj_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True

    # Check project is deleted
    assert db_session.get(Project, proj_id) is None

    # Refresh and verify tasks still exist and have project_id == None
    db_session.expire_all()
    db_task1 = db_session.get(Task, task1.id)
    db_task2 = db_session.get(Task, task2.id)

    assert db_task1 is not None
    assert db_task1.title == "Task 1 under project"
    assert db_task1.project_id is None

    assert db_task2 is not None
    assert db_task2.title == "Task 2 under project"
    assert db_task2.project_id is None


# ---------------- 3. HABITS DOMAIN ----------------
def test_delete_habit_tool_unauthorized_keeps_row_in_db(db_session: Session):
    registry = get_default_tool_registry()
    habit_svc = HabitService(db_session)
    habit = habit_svc.create_habit(HabitCreate(name="Daily Exercise", frequency="daily"))
    habit_id = habit.id

    res = registry.execute_tool(
        "delete_habit",
        {"habit_id": habit_id},
        db_session,
        destructive_authorized=False,
    )
    assert res["success"] is False
    assert "explicit user authorization" in res["error"]

    db_habit = db_session.get(Habit, habit_id)
    assert db_habit is not None
    assert db_habit.name == "Daily Exercise"


def test_delete_habit_tool_authorized_deletes_row_from_db(db_session: Session):
    registry = get_default_tool_registry()
    habit_svc = HabitService(db_session)
    habit = habit_svc.create_habit(HabitCreate(name="Temporary Habit", frequency="daily"))
    habit_id = habit.id

    res = registry.execute_tool(
        "delete_habit",
        {"habit_id": habit_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True
    assert f"Habit #{habit_id} deleted successfully" in res["data"]["message"]

    db_habit = db_session.get(Habit, habit_id)
    assert db_habit is None


def test_delete_habit_tool_argument_injection_resistant(db_session: Session):
    registry = get_default_tool_registry()
    habit_svc = HabitService(db_session)
    habit = habit_svc.create_habit(HabitCreate(name="Protected Habit", frequency="daily"))
    habit_id = habit.id

    injections = [
        {"habit_id": habit_id, "authorized": True},
        {"habit_id": habit_id, "authorize_destructive": True},
        {"habit_id": habit_id, "destructive_authorized": True},
    ]
    for args in injections:
        res = registry.execute_tool(
            "delete_habit",
            args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert db_session.get(Habit, habit_id) is not None


# ---------------- 4. POMODORO DOMAIN ----------------
def test_delete_pomodoro_session_tool_unauthorized_keeps_row_in_db(db_session: Session):
    registry = get_default_tool_registry()
    pomo_svc = PomodoroSessionService(db_session)
    session_obj = pomo_svc.start_session()
    session_id = session_obj.id

    res = registry.execute_tool(
        "delete_pomodoro_session",
        {"session_id": session_id},
        db_session,
        destructive_authorized=False,
    )
    assert res["success"] is False
    assert "explicit user authorization" in res["error"]

    db_session_obj = db_session.get(PomodoroSession, session_id)
    assert db_session_obj is not None


def test_delete_pomodoro_session_tool_authorized_deletes_row_from_db(db_session: Session):
    registry = get_default_tool_registry()
    pomo_svc = PomodoroSessionService(db_session)
    session_obj = pomo_svc.start_session()
    session_id = session_obj.id

    res = registry.execute_tool(
        "delete_pomodoro_session",
        {"session_id": session_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True
    assert f"Pomodoro session #{session_id} deleted successfully" in res["data"]["message"]

    db_session_obj = db_session.get(PomodoroSession, session_id)
    assert db_session_obj is None


def test_delete_pomodoro_session_tool_argument_injection_resistant(db_session: Session):
    registry = get_default_tool_registry()
    pomo_svc = PomodoroSessionService(db_session)
    session_obj = pomo_svc.start_session()
    session_id = session_obj.id

    injections = [
        {"session_id": session_id, "authorized": True},
        {"session_id": session_id, "authorize_destructive": True},
        {"session_id": session_id, "destructive_authorized": True},
    ]
    for args in injections:
        res = registry.execute_tool(
            "delete_pomodoro_session",
            args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert db_session.get(PomodoroSession, session_id) is not None


# ---------------- 5. REMINDERS DOMAIN ----------------
def test_delete_reminder_tool_unauthorized_keeps_row_in_db(db_session: Session):
    registry = get_default_tool_registry()
    rem_svc = ReminderService(db_session)
    rem = rem_svc.create_reminder(ReminderCreate(message="Call dentist", remind_at=datetime.now(timezone.utc)))
    rem_id = rem.id

    res = registry.execute_tool(
        "delete_reminder",
        {"reminder_id": rem_id},
        db_session,
        destructive_authorized=False,
    )
    assert res["success"] is False
    assert "explicit user authorization" in res["error"]

    db_rem = db_session.get(Reminder, rem_id)
    assert db_rem is not None
    assert db_rem.message == "Call dentist"


def test_delete_reminder_tool_authorized_deletes_row_from_db(db_session: Session):
    registry = get_default_tool_registry()
    rem_svc = ReminderService(db_session)
    rem = rem_svc.create_reminder(ReminderCreate(message="Temporary reminder", remind_at=datetime.now(timezone.utc)))
    rem_id = rem.id

    res = registry.execute_tool(
        "delete_reminder",
        {"reminder_id": rem_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True
    assert f"Reminder #{rem_id} deleted successfully" in res["data"]["message"]

    db_rem = db_session.get(Reminder, rem_id)
    assert db_rem is None


def test_delete_reminder_tool_argument_injection_resistant(db_session: Session):
    registry = get_default_tool_registry()
    rem_svc = ReminderService(db_session)
    rem = rem_svc.create_reminder(ReminderCreate(message="Protected reminder", remind_at=datetime.now(timezone.utc)))
    rem_id = rem.id

    injections = [
        {"reminder_id": rem_id, "authorized": True},
        {"reminder_id": rem_id, "authorize_destructive": True},
        {"reminder_id": rem_id, "destructive_authorized": True},
    ]
    for args in injections:
        res = registry.execute_tool(
            "delete_reminder",
            args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert db_session.get(Reminder, rem_id) is not None


# ---------------- 6. SCHEDULE DOMAIN ----------------
def test_delete_schedule_item_tool_unauthorized_keeps_row_in_db(db_session: Session):
    registry = get_default_tool_registry()
    sched_svc = ScheduleService(db_session)
    item = sched_svc.create_schedule_item(
        ScheduleItemCreate(
            title="Team Sync",
            starts_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
        )
    )
    item_id = item.id

    res = registry.execute_tool(
        "delete_schedule_item",
        {"item_id": item_id},
        db_session,
        destructive_authorized=False,
    )
    assert res["success"] is False
    assert "explicit user authorization" in res["error"]

    db_item = db_session.get(ScheduleItem, item_id)
    assert db_item is not None
    assert db_item.title == "Team Sync"


def test_delete_schedule_item_tool_authorized_deletes_row_from_db(db_session: Session):
    registry = get_default_tool_registry()
    sched_svc = ScheduleService(db_session)
    item = sched_svc.create_schedule_item(
        ScheduleItemCreate(
            title="Temporary Event",
            starts_at=datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        )
    )
    item_id = item.id

    res = registry.execute_tool(
        "delete_schedule_item",
        {"item_id": item_id},
        db_session,
        destructive_authorized=True,
    )
    assert res["success"] is True
    assert f"Schedule item #{item_id} deleted successfully" in res["data"]["message"]

    db_item = db_session.get(ScheduleItem, item_id)
    assert db_item is None


def test_delete_schedule_item_tool_argument_injection_resistant(db_session: Session):
    registry = get_default_tool_registry()
    sched_svc = ScheduleService(db_session)
    item = sched_svc.create_schedule_item(
        ScheduleItemCreate(
            title="Protected Schedule Item",
            starts_at=datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc),
        )
    )
    item_id = item.id

    injections = [
        {"item_id": item_id, "authorized": True},
        {"item_id": item_id, "authorize_destructive": True},
        {"item_id": item_id, "destructive_authorized": True},
    ]
    for args in injections:
        res = registry.execute_tool(
            "delete_schedule_item",
            args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert db_session.get(ScheduleItem, item_id) is not None
