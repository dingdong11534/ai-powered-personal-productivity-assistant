"""Concrete implementations of AI tools calling domain services."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.tools.base import BaseTool
from app.ai.tools.registry import ToolRegistry
from app.core.permissions import PermissionScope
from app.external.client import ExternalRequestError
from app.external.weather import WeatherService
from app.files.service import FileService
from app.habits.schemas import HabitCreate

from app.habits.service import HabitService
from app.memories.schemas import MemoryCreate, MemoryUpdate
from app.memories.service import MemoryService
from app.notifications.service import NotificationService
from app.pomodoro.service import PomodoroSessionService
from app.projects.schemas import ProjectCreate
from app.projects.service import ProjectService
from app.reminders.schemas import ReminderCreate
from app.reminders.service import ReminderService
from app.scheduling.schemas import ScheduleItemCreate
from app.scheduling.service import ScheduleService
from app.storage.models import MemoryCategory
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


class DeleteTaskTool(BaseTool):
    name = "delete_task"
    description = "Permanently delete a task by ID. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "ID of the task to delete"},
        },
        "required": ["task_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = TaskService(session)
        svc.delete_task(args["task_id"])
        return {"success": True, "message": f"Task #{args['task_id']} deleted successfully."}


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


class DeleteProjectTool(BaseTool):
    name = "delete_project"
    description = "Permanently delete a project by ID. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "ID of project to delete"},
        },
        "required": ["project_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ProjectService(session)
        svc.delete_project(args["project_id"])
        return {"success": True, "message": f"Project #{args['project_id']} deleted successfully."}


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


class DeleteHabitTool(BaseTool):
    name = "delete_habit"
    description = "Permanently delete a habit tracker and its completions by ID. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "habit_id": {"type": "integer", "description": "ID of habit to delete"},
        },
        "required": ["habit_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = HabitService(session)
        svc.delete_habit(args["habit_id"])
        return {"success": True, "message": f"Habit #{args['habit_id']} deleted successfully."}


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


class DeletePomodoroSessionTool(BaseTool):
    name = "delete_pomodoro_session"
    description = "Permanently delete a Pomodoro session record by ID. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "session_id": {"type": "integer", "description": "ID of Pomodoro session to delete"},
        },
        "required": ["session_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = PomodoroSessionService(session)
        svc.delete_session(args["session_id"])
        return {"success": True, "message": f"Pomodoro session #{args['session_id']} deleted successfully."}


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


class DeleteReminderTool(BaseTool):
    name = "delete_reminder"
    description = "Permanently delete a reminder by ID. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "reminder_id": {"type": "integer", "description": "ID of reminder to delete"},
        },
        "required": ["reminder_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ReminderService(session)
        svc.delete_reminder(args["reminder_id"])
        return {"success": True, "message": f"Reminder #{args['reminder_id']} deleted successfully."}


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


class DeleteScheduleItemTool(BaseTool):
    name = "delete_schedule_item"
    description = "Permanently delete a schedule block by ID. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "item_id": {"type": "integer", "description": "ID of schedule item to delete"},
        },
        "required": ["item_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ScheduleService(session)
        svc.delete_schedule_item(args["item_id"])
        return {"success": True, "message": f"Schedule item #{args['item_id']} deleted successfully."}


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


# ---------------- MEMORIES ----------------
class RememberInformationTool(BaseTool):
    name = "remember_information"
    description = "Store a curated fact or preference worth remembering for future assistant interactions."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact or preference to remember"},
            "category": {
                "type": "string",
                "enum": ["preference", "goal", "project_context", "routine", "personal_context", "system_preference"],
                "default": "preference",
                "description": "Category of the memory",
            },
        },
        "required": ["content"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = MemoryService(session)
        cat_str = args.get("category", "preference")
        cat = MemoryCategory(cat_str)
        mem = svc.create_memory(MemoryCreate(content=args["content"], category=cat))
        return _to_dict(mem)


class ListMemoriesTool(BaseTool):
    name = "list_memories"
    description = "List stored active memories, optionally filtered by category."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "include_archived": {"type": "boolean", "default": False},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = MemoryService(session)
        mems = svc.list_memories(
            category=args.get("category"),
            include_archived=args.get("include_archived", False),
        )
        return {"memories": [_to_dict(m) for m in mems]}


class SearchMemoriesTool(BaseTool):
    name = "search_memories"
    description = "Search active stored memories by keyword query."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term"},
            "category": {"type": "string"},
        },
        "required": ["query"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = MemoryService(session)
        mems = svc.retrieve_relevant_memories(
            query=args["query"],
            category=args.get("category"),
            limit=10,
        )
        return {"memories": [_to_dict(m) for m in mems]}


class UpdateMemoryTool(BaseTool):
    name = "update_memory"
    description = "Update an existing memory's content or category."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer", "description": "ID of memory to update"},
            "content": {"type": "string"},
            "category": {"type": "string"},
        },
        "required": ["memory_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = MemoryService(session)
        cat = MemoryCategory(args["category"]) if args.get("category") else None
        mem = svc.update_memory(
            args["memory_id"],
            MemoryUpdate(content=args.get("content"), category=cat),
        )
        return _to_dict(mem)


class DeleteMemoryTool(BaseTool):
    name = "delete_memory"
    description = "Forget, archive, or delete a stored memory."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer", "description": "ID of memory to remove"},
            "hard_delete": {"type": "boolean", "default": False, "description": "Whether to permanently delete instead of archiving"},
        },
        "required": ["memory_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = MemoryService(session)
        if args.get("hard_delete"):
            svc.delete_memory(args["memory_id"])
            return {"success": True, "message": f"Memory #{args['memory_id']} permanently deleted."}
        else:
            mem = svc.archive_memory(args["memory_id"])
            return _to_dict(mem)


# ---------------- FILES / WORKSPACE ----------------
class ListWorkspaceFilesTool(BaseTool):
    name = "list_workspace_files"
    description = "List files and subdirectories within the sandboxed assistant workspace."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "sub_path": {
                "type": "string",
                "default": "",
                "description": "Optional subdirectory within the workspace to list.",
            },
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = FileService()
        files = svc.list_files(sub_path=args.get("sub_path", ""))
        return {"files": [_to_dict(f) for f in files]}


class ReadWorkspaceFileTool(BaseTool):
    name = "read_workspace_file"
    description = "Read the text content of a file located in the sandboxed workspace."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file path within the workspace.",
            },
        },
        "required": ["path"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = FileService()
        result = svc.read_file(relative_path=args["path"])
        return _to_dict(result)


class CreateWorkspaceFileTool(BaseTool):
    name = "create_workspace_file"
    description = "Create a new UTF-8 text file in the sandboxed workspace. Fails if it already exists."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file path within the workspace.",
            },
            "content": {
                "type": "string",
                "description": "Text content to write into the file.",
            },
        },
        "required": ["path", "content"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = FileService()
        result = svc.write_file(
            relative_path=args["path"],
            content=args["content"],
            overwrite=False,
        )
        return _to_dict(result)


class UpdateWorkspaceFileTool(BaseTool):
    name = "update_workspace_file"
    description = "Replace an existing UTF-8 text file in the sandboxed workspace. Requires explicit user authorization."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Existing relative file path within the workspace."},
            "content": {"type": "string", "description": "Replacement text content."},
        },
        "required": ["path", "content"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = FileService()
        target = svc.resolve_and_validate_path(args["path"])
        if not target.exists():
            from app.files.exceptions import FileNotFoundInWorkspaceError

            raise FileNotFoundInWorkspaceError(f"File '{args['path']}' not found in workspace.")
        return _to_dict(svc.write_file(args["path"], args["content"], overwrite=True))


class SearchWorkspaceFilesTool(BaseTool):
    name = "search_workspace_files"
    description = "Search for files in the workspace matching a query in filename or text content."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search term to match against file paths and content.",
            },
            "sub_path": {
                "type": "string",
                "default": "",
                "description": "Subdirectory to restrict search.",
            },
        },
        "required": ["query"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = FileService()
        files = svc.search_files(
            query=args["query"],
            sub_path=args.get("sub_path", ""),
        )
        return {"files": [_to_dict(f) for f in files]}


class DeleteWorkspaceFileTool(BaseTool):
    name = "delete_workspace_file"
    description = "Delete a file or directory inside the sandboxed workspace."
    scope = PermissionScope.DESTRUCTIVE
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file or folder path within the workspace to delete.",
            },
        },
        "required": ["path"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = FileService()
        svc.delete_file(relative_path=args["path"])
        return {"success": True, "message": f"Path '{args['path']}' deleted successfully."}


# ---------------- EXTERNAL: WEATHER ----------------
class GetCurrentWeatherTool(BaseTool):
    """Fetch current weather conditions for any location via Open-Meteo.

    Scope: EXTERNAL — routes through the SSRF-safe ExternalHttpClient.
    Security: the target domain (api.open-meteo.com) is fixed in WeatherService;
    the AI can only supply the `location` string, not the URL or domain.
    """

    name = "get_current_weather"
    description = (
        "Get the current weather conditions for a location (city name, region, or country). "
        "Returns temperature (Celsius), humidity, wind speed, and a plain-English description "
        "of current conditions. Uses the free Open-Meteo API — no API key required."
    )
    scope = PermissionScope.EXTERNAL
    parameters_schema = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Name of the city or location to get weather for (e.g. 'London', 'New York', 'Tokyo').",
            }
        },
        "required": ["location"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        location = args.get("location", "").strip()
        if not location:
            return {"success": False, "error": "location is required"}
        try:
            svc = WeatherService()
            weather = svc.get_current_weather(location)
            return {
                "success": True,
                "location": f"{weather['location_name']}, {weather['country']}".strip(", "),
                "temperature": f"{weather['temperature_c']}°C",
                "humidity": f"{weather['humidity_pct']}%",
                "wind_speed": f"{weather['wind_speed_mph']} mph",
                "conditions": weather["conditions"],
                "as_of": weather["data_time"],
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ExternalRequestError as e:
            return {"success": False, "error": f"Weather service error: {e}"}


def get_default_tool_registry() -> ToolRegistry:
    """Helper to construct a ToolRegistry populated with all standard tools."""
    registry = ToolRegistry()
    registry.register(CreateTaskTool())
    registry.register(UpdateTaskTool())
    registry.register(ListTasksTool())
    registry.register(SearchTasksTool())
    registry.register(CompleteTaskTool())
    registry.register(DeleteTaskTool())

    registry.register(CreateProjectTool())
    registry.register(ListProjectsTool())
    registry.register(ArchiveProjectTool())
    registry.register(DeleteProjectTool())

    registry.register(CreateHabitTool())
    registry.register(CompleteHabitTool())
    registry.register(GetHabitStatisticsTool())
    registry.register(DeleteHabitTool())

    registry.register(StartPomodoroTool())
    registry.register(EndPomodoroTool())
    registry.register(DeletePomodoroSessionTool())

    registry.register(CreateReminderTool())
    registry.register(ListRemindersTool())
    registry.register(DeleteReminderTool())

    registry.register(CreateScheduleItemTool())
    registry.register(ListScheduleTool())
    registry.register(DeleteScheduleItemTool())

    registry.register(ListNotificationsTool())
    registry.register(MarkNotificationReadTool())

    registry.register(RememberInformationTool())
    registry.register(ListMemoriesTool())
    registry.register(SearchMemoriesTool())
    registry.register(UpdateMemoryTool())
    registry.register(DeleteMemoryTool())

    registry.register(ListWorkspaceFilesTool())
    registry.register(ReadWorkspaceFileTool())
    registry.register(CreateWorkspaceFileTool())
    registry.register(UpdateWorkspaceFileTool())
    registry.register(SearchWorkspaceFilesTool())
    registry.register(DeleteWorkspaceFileTool())

    registry.register(GetCurrentWeatherTool())
    return registry
