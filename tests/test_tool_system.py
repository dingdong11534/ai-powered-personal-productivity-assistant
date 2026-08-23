"""Tests for AI Tool registration, validation, permissions, and execution."""

import pytest
from app.ai.tools.implementations import (
    CompleteHabitTool,
    CreateScheduleItemTool,
    CreateTaskTool,
    UpdateTaskTool,
    get_default_tool_registry,
)
from app.ai.tools.registry import ToolRegistry
from app.core.permissions import PermissionChecker, PermissionDenied, PermissionRequest, PermissionScope
from app.habits.schemas import HabitCreate
from app.habits.service import HabitService
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService


def test_tool_registry_registration_and_schemas():
    registry = get_default_tool_registry()
    schemas = registry.get_tools_schema()

    assert len(schemas) >= 19
    names = [s["function"]["name"] for s in schemas]
    assert "create_task" in names
    assert "update_task" in names
    assert "complete_habit" in names
    assert "create_schedule_item" in names


def test_task_creation_through_ai_tool(db_session):
    registry = get_default_tool_registry()
    res = registry.execute_tool(
        "create_task",
        {"title": "Tool Created Task", "priority": 1},
        db_session,
    )
    assert res["success"] is True
    data = res["data"]
    assert data["id"] is not None
    assert data["title"] == "Tool Created Task"
    assert data["priority"] == 1

    # Verify task exists in task service
    task = TaskService(db_session).get_task(data["id"])
    assert task.title == "Tool Created Task"


def test_task_update_through_ai_tool(db_session):
    task_svc = TaskService(db_session)
    task = task_svc.create_task(TaskCreate(title="Original Title"))

    registry = get_default_tool_registry()
    res = registry.execute_tool(
        "update_task",
        {"task_id": task.id, "title": "Updated Title", "status": "done"},
        db_session,
    )
    assert res["success"] is True
    assert res["data"]["title"] == "Updated Title"
    assert res["data"]["status"] == "done"


def test_habit_completion_through_ai_tool(db_session):
    habit_svc = HabitService(db_session)
    habit = habit_svc.create_habit(HabitCreate(name="Daily Meditation", frequency="daily"))

    registry = get_default_tool_registry()
    res = registry.execute_tool(
        "complete_habit",
        {"habit_id": habit.id},
        db_session,
    )
    assert res["success"] is True
    assert res["data"]["habit_id"] == habit.id


def test_schedule_creation_through_ai_tool(db_session):
    registry = get_default_tool_registry()
    res = registry.execute_tool(
        "create_schedule_item",
        {
            "title": "Focus Block",
            "starts_at": "2026-08-24T10:00:00",
            "ends_at": "2026-08-24T11:00:00",
        },
        db_session,
    )
    assert res["success"] is True
    assert res["data"]["title"] == "Focus Block"


def test_invalid_tool_request(db_session):
    registry = get_default_tool_registry()
    res = registry.execute_tool(
        "non_existent_tool",
        {},
        db_session,
    )
    assert res["success"] is False
    assert "not registered" in res["error"]


def test_tool_permission_denial(db_session):
    class RejectingChecker(PermissionChecker):
        def check(self, request: PermissionRequest) -> None:
            raise PermissionDenied("Blocked for test")

    registry = ToolRegistry(permission_checker=RejectingChecker())
    registry.register(CreateTaskTool())

    res = registry.execute_tool("create_task", {"title": "Block me"}, db_session)
    assert res["success"] is False
    assert "Permission denied" in res["error"]
