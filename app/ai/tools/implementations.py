"""Concrete implementations of AI tools calling domain services."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.tools.base import BaseTool
from app.ai.tools.registry import ToolRegistry
from app.core.permissions import PermissionScope
from app.habits.schemas import HabitCreate
from app.habits.service import HabitService
from app.notifications.service import NotificationService
from app.pomodoro.service import PomodoroSessionService
from app.projects.schemas import ProjectCreate
from app.projects.service import ProjectService
from app.reminders.schemas import ReminderCreate
from app.reminders.service import ReminderService
from app.scheduling.schemas import ScheduleItemCreate
from app.scheduling.service import ScheduleService
from app.tasks.schemas import TaskCreate, TaskUpdate
from app.tasks.service import TaskService


def _to_dict(obj: Any) -> dict[str, Any]:
    """Helper to convert Pydantic schema or SQLAlchemy ORM model to dictionary."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__table__"):
        res = {}
        for c in obj.__table__.columns:
            val = getattr(obj, c.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            res[c.name] = val
        return res
    return dict(obj)


# ---------------- TASKS ----------------
class CreateTaskTool(BaseTool):
    name = "create_task"
    description = "Create a new task in the productivity system."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Title of the task"},
            "description": {"type": "string", "description": "Optional details"},
            "priority": {"type": "integer", "description": "Priority (1=Critical, 2=High, 3=Medium, 4=Low)", "default": 2},
            "project_id": {"type": "integer", "description": "Optional project ID"},
            "deadline": {"type": "string", "description": "Optional ISO format deadline datetime"},
        },
        "required": ["title"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = TaskService(session)
        dl = datetime.fromisoformat(args["deadline"]) if args.get("deadline") else None
        t_data = TaskCreate(
            title=args["title"],
            description=args.get("description"),
            priority=args.get("priority", 2),
            project_id=args.get("project_id"),
            deadline=dl,
        )
        task = svc.create_task(t_data)
        return _to_dict(task)


class UpdateTaskTool(BaseTool):
    name = "update_task"
    description = "Partially update an existing task."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "ID of the task to update"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "string", "enum": ["todo", "in_progress", "done", "cancelled"]},
            "priority": {"type": "integer"},
            "project_id": {"type": "integer"},
        },
        "required": ["task_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = TaskService(session)
        task_id = args["task_id"]
        update_kwargs = {}
        for key in ("title", "description", "status", "priority", "project_id"):
            if key in args and args[key] is not None:
                update_kwargs[key] = args[key]
        t_data = TaskUpdate(**update_kwargs)
        task = svc.update_task(task_id, t_data)
        return _to_dict(task)


class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = "List and filter tasks."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "priority": {"type": "integer"},
            "project_id": {"type": "integer"},
            "completed": {"type": "boolean"},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = TaskService(session)
        tasks = svc.list_tasks(
            status=args.get("status"),
            priority=args.get("priority"),
            project_id=args.get("project_id"),
            completed=args.get("completed"),
        )
        return {"tasks": [_to_dict(t) for t in tasks]}


class SearchTasksTool(BaseTool):
    name = "search_tasks"
    description = "Search tasks by title or description string."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term"},
        },
        "required": ["query"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = TaskService(session)
        tasks = svc.list_tasks(search=args["query"])
        return {"tasks": [_to_dict(t) for t in tasks]}


class CompleteTaskTool(BaseTool):
    name = "complete_task"
    description = "Mark a task as done."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "ID of the task to complete"},
        },
        "required": ["task_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = TaskService(session)
        task = svc.update_task(args["task_id"], TaskUpdate(status="done"))
        return _to_dict(task)


# ---------------- PROJECTS ----------------
class CreateProjectTool(BaseTool):
    name = "create_project"
    description = "Create a new project."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Project name"},
            "description": {"type": "string"},
            "color": {"type": "string"},
        },
        "required": ["name"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ProjectService(session)
        proj = svc.create_project(ProjectCreate(
            name=args["name"],
            description=args.get("description"),
            color=args.get("color"),
        ))
        return _to_dict(proj)


class ListProjectsTool(BaseTool):
    name = "list_projects"
    description = "List all active projects."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "include_archived": {"type": "boolean", "default": False},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ProjectService(session)
        projs = svc.list_projects(include_archived=args.get("include_archived", False))
        return {"projects": [_to_dict(p) for p in projs]}


class ArchiveProjectTool(BaseTool):
    name = "archive_project"
    description = "Archive an existing project."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "ID of project to archive"},
        },
        "required": ["project_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ProjectService(session)
        proj = svc.archive_project(args["project_id"])
        return _to_dict(proj)


# ---------------- HABITS ----------------
class CreateHabitTool(BaseTool):
    name = "create_habit"
    description = "Create a new habit tracker."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of habit"},
            "frequency": {"type": "string", "enum": ["daily", "weekly", "monthly"], "default": "daily"},
            "target_count": {"type": "integer", "default": 1},
        },
        "required": ["name"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = HabitService(session)
        habit = svc.create_habit(HabitCreate(
            name=args["name"],
            frequency=args.get("frequency", "daily"),
            target_count=args.get("target_count", 1),
        ))
        return _to_dict(habit)


class CompleteHabitTool(BaseTool):
    name = "complete_habit"
    description = "Record a completion for a habit."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "habit_id": {"type": "integer", "description": "ID of habit"},
        },
        "required": ["habit_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = HabitService(session)
        comp = svc.record_completion(args["habit_id"])
        return _to_dict(comp)


class GetHabitStatisticsTool(BaseTool):
    name = "get_habit_statistics"
    description = "Get streaks and completion stats for a habit."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "habit_id": {"type": "integer", "description": "ID of habit"},
        },
        "required": ["habit_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = HabitService(session)
        stats = svc.get_statistics(args["habit_id"])
        return _to_dict(stats)


# ---------------- POMODORO ----------------
class StartPomodoroTool(BaseTool):
    name = "start_pomodoro"
    description = "Start a new Pomodoro focus session."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "Optional task ID to associate"},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = PomodoroSessionService(session)
        pomo = svc.start_session(task_id=args.get("task_id"))
        return _to_dict(pomo)


class EndPomodoroTool(BaseTool):
    name = "end_pomodoro"
    description = "End an active Pomodoro focus session."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "session_id": {"type": "integer", "description": "Session ID"},
            "interrupted": {"type": "boolean", "default": False},
        },
        "required": ["session_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = PomodoroSessionService(session)
        pomo = svc.end_session(
            args["session_id"],
            interrupted=args.get("interrupted", False),
        )
        return _to_dict(pomo)


# ---------------- REMINDERS ----------------
class CreateReminderTool(BaseTool):
    name = "create_reminder"
    description = "Create a reminder."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Reminder text"},
            "remind_at": {"type": "string", "description": "ISO datetime string"},
            "task_id": {"type": "integer"},
        },
        "required": ["message", "remind_at"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ReminderService(session)
        dt = datetime.fromisoformat(args["remind_at"])
        rem = svc.create_reminder(ReminderCreate(
            message=args["message"],
            remind_at=dt,
            task_id=args.get("task_id"),
        ))
        return _to_dict(rem)


class ListRemindersTool(BaseTool):
    name = "list_reminders"
    description = "List upcoming or due reminders."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "upcoming": {"type": "boolean"},
            "due": {"type": "boolean"},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ReminderService(session)
        if args.get("upcoming"):
            rems = svc.list_upcoming_reminders()
        elif args.get("due"):
            rems = svc.list_due_reminders()
        else:
            rems = svc.list_reminders()
        return {"reminders": [_to_dict(r) for r in rems]}


# ---------------- SCHEDULE ----------------
class CreateScheduleItemTool(BaseTool):
    name = "create_schedule_item"
    description = "Create a local schedule item."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "starts_at": {"type": "string", "description": "ISO start time"},
            "ends_at": {"type": "string", "description": "ISO end time"},
            "task_id": {"type": "integer"},
        },
        "required": ["title", "starts_at", "ends_at"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ScheduleService(session)
        s_item = svc.create_schedule_item(ScheduleItemCreate(
            title=args["title"],
            starts_at=datetime.fromisoformat(args["starts_at"]),
            ends_at=datetime.fromisoformat(args["ends_at"]),
            task_id=args.get("task_id"),
        ))
        return _to_dict(s_item)


class ListScheduleTool(BaseTool):
    name = "list_schedule"
    description = "List schedule items."
    scope = PermissionScope.READ
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ScheduleService(session)
        items = svc.list_schedule_items()
        return {"schedule_items": [_to_dict(s) for s in items]}


# ---------------- NOTIFICATIONS ----------------
class ListNotificationsTool(BaseTool):
    name = "list_notifications"
    description = "List notification records."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "unread_only": {"type": "boolean", "default": False},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = NotificationService(session)
        notifs = svc.list_notifications(unread_only=args.get("unread_only", False))
        return {"notifications": [_to_dict(n) for n in notifs]}


class MarkNotificationReadTool(BaseTool):
    name = "mark_notification_read"
    description = "Mark a notification record as read."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "notification_id": {"type": "integer"},
        },
        "required": ["notification_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = NotificationService(session)
        notif = svc.mark_read(args["notification_id"])
        return _to_dict(notif)


def get_default_tool_registry() -> ToolRegistry:
    """Helper to construct a ToolRegistry populated with all 19 standard tools."""
    registry = ToolRegistry()
    registry.register(CreateTaskTool())
    registry.register(UpdateTaskTool())
    registry.register(ListTasksTool())
    registry.register(SearchTasksTool())
    registry.register(CompleteTaskTool())

    registry.register(CreateProjectTool())
    registry.register(ListProjectsTool())
    registry.register(ArchiveProjectTool())

    registry.register(CreateHabitTool())
    registry.register(CompleteHabitTool())
    registry.register(GetHabitStatisticsTool())

    registry.register(StartPomodoroTool())
    registry.register(EndPomodoroTool())

    registry.register(CreateReminderTool())
    registry.register(ListRemindersTool())

    registry.register(CreateScheduleItemTool())
    registry.register(ListScheduleTool())

    registry.register(ListNotificationsTool())
    registry.register(MarkNotificationReadTool())
    return registry
