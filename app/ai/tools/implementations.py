"""Concrete implementations of AI tools calling domain services."""

from datetime import datetime, timezone
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
from app.notifications.service import NotificationService, record_activity
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
        title = (
            args.get("title")
            or args.get("name")
            or args.get("task_name")
            or args.get("description")
            or "New Task"
        )
        desc = args.get("description")
        if desc == title:
            desc = None

        raw_p = args.get("priority", 2)
        if isinstance(raw_p, str):
            p_map = {"critical": 1, "highest": 1, "urgent": 1, "high": 2, "medium": 3, "low": 4}
            priority = p_map.get(raw_p.lower(), 2)
        else:
            try:
                priority = int(raw_p)
            except Exception:
                priority = 2

        task_user_id = args.get("user_id") or 1
        proj_id = args.get("project_id")
        if not proj_id and (args.get("project_name") or args.get("project")):
            p_name = str(args.get("project_name") or args.get("project")).lower()
            p_svc = ProjectService(session)
            for p in p_svc.list_projects(user_id=task_user_id):
                if p_name in p.name.lower():
                    proj_id = p.id
                    break
        elif isinstance(proj_id, str) and not proj_id.isdigit():
            p_name = proj_id.lower()
            p_svc = ProjectService(session)
            for p in p_svc.list_projects(user_id=task_user_id):
                if p_name in p.name.lower():
                    proj_id = p.id
                    break
        elif proj_id is not None:
            try:
                proj_id = int(proj_id)
            except Exception:
                pass

        dl = datetime.fromisoformat(args["deadline"]) if args.get("deadline") else None
        t_data = TaskCreate(
            title=str(title).strip(),
            description=desc,
            priority=priority,
            project_id=proj_id,
            deadline=dl,
        )
        task = svc.create_task(t_data, user_id=task_user_id)
        record_activity(session, f"Task created: {task.title}", body=task.description, source="task", user_id=task_user_id)
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
        user_id = args.get("user_id")
        task_id = args.get("task_id") or args.get("id")
        if not task_id and (args.get("task_title") or args.get("title")):
            t_title = str(args.get("task_title") or args.get("title")).lower()
            for t in svc.list_tasks(user_id=user_id):
                if t_title in t.title.lower():
                    task_id = t.id
                    break
        elif isinstance(task_id, str) and not task_id.isdigit():
            t_title = task_id.lower()
            for t in svc.list_tasks(user_id=user_id):
                if t_title in t.title.lower():
                    task_id = t.id
                    break
        if not task_id:
            raise ValueError("Task ID is required for update_task")
        task_id = int(task_id)
        update_kwargs = {}
        for key in ("title", "description", "status", "priority", "project_id"):
            if key in args and args[key] is not None:
                update_kwargs[key] = args[key]
        if "project_id" not in update_kwargs and (args.get("project_name") or args.get("project")):
            p_name = str(args.get("project_name") or args.get("project")).lower()
            if p_name in ("none", "null", "clear", "unlink"):
                update_kwargs["project_id"] = None
            else:
                p_svc = ProjectService(session)
                for p in p_svc.list_projects(user_id=user_id):
                    if p_name in p.name.lower():
                        update_kwargs["project_id"] = p.id
                        break
        elif "project_id" in update_kwargs:
            val = update_kwargs["project_id"]
            if isinstance(val, str) and not val.isdigit():
                p_name = val.lower()
                if p_name in ("none", "null", "clear", "unlink"):
                    update_kwargs["project_id"] = None
                else:
                    p_svc = ProjectService(session)
                    for p in p_svc.list_projects(user_id=user_id):
                        if p_name in p.name.lower():
                            update_kwargs["project_id"] = p.id
                            break
        t_data = TaskUpdate(**update_kwargs)
        task = svc.update_task(task_id, t_data)
        record_activity(session, f"Task updated: {task.title}", source="task", user_id=user_id or task.user_id)
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
            user_id=args.get("user_id"),
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
        tasks = svc.list_tasks(search=args["query"], user_id=args.get("user_id"))
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
        raw_id = args.get("task_id") or args.get("id")
        user_id = args.get("user_id")
        if not raw_id:
            title = args.get("title") or args.get("task_name")
            if title:
                matches = svc.list_tasks(search=str(title), user_id=user_id)
                if matches:
                    raw_id = matches[0].id
        if not raw_id:
            raise ValueError("Task ID is required for complete_task")
        task = svc.update_task(int(raw_id), TaskUpdate(status="done"))
        record_activity(session, f"Task completed: {task.title}", source="task", user_id=user_id or task.user_id)
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
        raw_id = args.get("task_id") or args.get("id")
        user_id = args.get("user_id")
        if raw_id is None:
            # Fallback: title lookup if model passed title
            title = args.get("title") or args.get("task_name")
            if title:
                matches = svc.list_tasks(search=str(title), user_id=user_id)
                if matches:
                    raw_id = matches[0].id
        if raw_id is None:
            return {"success": False, "error": "task_id is required"}
        try:
            task_id = int(raw_id)
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid task_id: {raw_id}"}
        svc.delete_task(task_id)
        record_activity(session, f"Task deleted: ID #{task_id}", source="task", user_id=user_id)
        return {"success": True, "message": f"Task #{task_id} deleted successfully."}


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
        name = args.get("name") or args.get("title") or "New Project"
        proj_user_id = args.get("user_id") or 1
        proj = svc.create_project(
            ProjectCreate(
                name=str(name).strip(),
                description=args.get("description"),
                color=args.get("color"),
            ),
            user_id=proj_user_id,
        )
        record_activity(session, f"Project created: {proj.name}", body=proj.description, source="project", user_id=proj_user_id)
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
        projs = svc.list_projects(
            include_archived=args.get("include_archived", False),
            user_id=args.get("user_id"),
        )
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
        project_id = args.get("project_id") or args.get("id")
        user_id = args.get("user_id")
        if not project_id:
            raise ValueError("project_id is required for archive_project")
        proj = svc.archive_project(project_id)
        record_activity(session, f"Project archived: ID #{project_id}", source="project", user_id=user_id or proj.user_id)
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
        project_id = args.get("project_id") or args.get("id")
        user_id = args.get("user_id")
        if not project_id:
            raise ValueError("project_id is required for delete_project")
        svc.delete_project(project_id)
        record_activity(session, f"Project deleted: ID #{project_id}", source="project", user_id=user_id)
        return {"success": True, "message": f"Project #{project_id} deleted successfully."}


class AssignTaskToProjectTool(BaseTool):
    """Assign or connect an existing task to a project (or unlink it)."""

    name = "assign_task_to_project"
    description = "Connect an existing task to a project by ID or project name, or unlink it."
    scope = PermissionScope.WRITE
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "ID of the task to assign"},
            "project_id": {"type": "integer", "description": "ID of the target project, or null to unlink"},
            "project_name": {"type": "string", "description": "Optional name of the target project (or 'none' to unlink)"},
        },
        "required": ["task_id"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        task_svc = TaskService(session)
        proj_svc = ProjectService(session)
        user_id = args.get("user_id")
        raw_task_id = args.get("task_id") or args.get("id")
        if not raw_task_id and (args.get("task_title") or args.get("title")):
            t_title = str(args.get("task_title") or args.get("title")).lower()
            for t in task_svc.list_tasks(user_id=user_id):
                if t_title in t.title.lower():
                    raw_task_id = t.id
                    break
        elif isinstance(raw_task_id, str) and not raw_task_id.isdigit():
            t_title = raw_task_id.lower()
            for t in task_svc.list_tasks(user_id=user_id):
                if t_title in t.title.lower():
                    raw_task_id = t.id
                    break
        if not raw_task_id:
            raise ValueError("task_id is required")
        task_id = int(raw_task_id)

        target_proj_id = args.get("project_id")
        if target_proj_id is None and (args.get("project_name") or args.get("project")):
            p_name = str(args.get("project_name") or args.get("project")).lower()
            if p_name in ("none", "null", "unlink", "clear"):
                target_proj_id = None
            else:
                for p in proj_svc.list_projects(user_id=user_id):
                    if p_name in p.name.lower():
                        target_proj_id = p.id
                        break

        task = task_svc.update_task(task_id, TaskUpdate(project_id=target_proj_id))
        proj_title = "None"
        if target_proj_id:
            try:
                p = proj_svc.get_project(target_proj_id)
                proj_title = p.name if p else f"#{target_proj_id}"
            except Exception:
                proj_title = f"#{target_proj_id}"
        record_activity(session, f"Task #{task_id} connected to project: {proj_title}", source="project", user_id=user_id or task.user_id)
        return {
            "success": True,
            "task_id": task.id,
            "task_title": task.title,
            "project_id": target_proj_id,
            "project_name": proj_title,
            "message": f"Task '{task.title}' connected to project '{proj_title}'.",
        }


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
        name = args.get("name") or args.get("title") or "New Habit"
        freq = str(args.get("frequency", "daily")).lower()
        if freq not in ("daily", "weekly", "monthly"):
            freq = "daily"
        raw_count = args.get("target_count")
        try:
            target_count = int(raw_count) if raw_count is not None else 1
        except Exception:
            target_count = 1
        if target_count < 1 or target_count > 100:
            target_count = 1
        habit_user_id = args.get("user_id") or 1
        habit = svc.create_habit(
            HabitCreate(
                name=str(name).strip(),
                frequency=freq,
                target_count=target_count,
            ),
            user_id=habit_user_id,
        )
        record_activity(session, f"Habit created: {habit.name}", source="habit", user_id=habit_user_id)
        return _to_dict(habit)


class ListHabitsTool(BaseTool):
    name = "list_habits"
    description = "List all tracked habits and routines."
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "include_archived": {"type": "boolean", "default": False},
        },
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = HabitService(session)
        habits = svc.list_habits(
            include_archived=args.get("include_archived", False),
            user_id=args.get("user_id"),
        )
        return {"habits": [_to_dict(h) for h in habits]}


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
        user_id = args.get("user_id")
        raw_id = args.get("habit_id") or args.get("id")
        if not raw_id:
            name = args.get("name") or args.get("habit_name") or args.get("title")
            if name:
                habits = svc.list_habits(user_id=user_id)
                for h in habits:
                    if str(name).lower() in h.name.lower():
                        raw_id = h.id
                        break
        if not raw_id:
            raise ValueError("Habit ID is required for complete_habit")
        comp = svc.record_completion(int(raw_id))
        res = _to_dict(comp)
        try:
            h = svc.get_habit(int(raw_id))
            if h:
                res["habit_name"] = h.name
                res["habit_id"] = h.id
                record_activity(session, f"Habit completed: {h.name}", source="habit", user_id=user_id or h.user_id)
        except Exception:
            record_activity(session, f"Habit completed: ID #{raw_id}", source="habit", user_id=user_id)
        return res


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
        user_id = args.get("user_id")
        raw_id = args.get("habit_id") or args.get("id")
        if not raw_id:
            name = args.get("name") or args.get("habit_name")
            if name:
                habits = svc.list_habits(user_id=user_id)
                for h in habits:
                    if str(name).lower() in h.name.lower():
                        raw_id = h.id
                        break
        if not raw_id:
            raise ValueError("Habit ID is required for get_habit_statistics")
        stats = svc.get_statistics(int(raw_id))
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
        user_id = args.get("user_id")
        raw_id = args.get("habit_id") or args.get("id")
        if not raw_id:
            name = args.get("name") or args.get("habit_name") or args.get("title")
            if name:
                habits = svc.list_habits(user_id=user_id)
                for h in habits:
                    if str(name).lower() in h.name.lower():
                        raw_id = h.id
                        break
        if not raw_id:
            return {"success": False, "error": "habit_id is required"}
        svc.delete_habit(int(raw_id))
        record_activity(session, f"Habit deleted: ID #{raw_id}", source="habit", user_id=user_id)
        return {"success": True, "message": f"Habit #{raw_id} deleted successfully.", "habit_id": int(raw_id)}


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
        pomo_user_id = args.get("user_id") or 1
        pomo = svc.start_session(task_id=args.get("task_id"), user_id=pomo_user_id)
        p_title = getattr(pomo, "title", None) or "Focus session"
        record_activity(session, f"Pomodoro started: {p_title}", source="pomodoro", user_id=pomo_user_id)
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
        record_activity(session, f"Pomodoro ended: session #{args['session_id']}", source="pomodoro", user_id=args.get("user_id"))
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
        record_activity(session, f"Pomodoro session deleted: ID #{args['session_id']}", source="pomodoro", user_id=args.get("user_id"))
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
        msg = args.get("message") or args.get("title") or args.get("text") or "Reminder"
        raw_dt = args.get("remind_at") or args.get("time") or args.get("datetime")
        dt = None
        if raw_dt:
            try:
                dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
            except Exception:
                pass
        if dt is None:
            from datetime import timedelta
            dt = datetime.now(timezone.utc) + timedelta(hours=1)
        rem_user_id = args.get("user_id") or 1
        rem = svc.create_reminder(
            ReminderCreate(
                message=str(msg).strip(),
                remind_at=dt,
                task_id=args.get("task_id"),
            ),
            user_id=rem_user_id,
        )
        record_activity(session, f"Reminder set: {rem.message}", source="reminder", user_id=rem_user_id)
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
        user_id = args.get("user_id")
        if args.get("upcoming"):
            rems = svc.list_upcoming_reminders(user_id=user_id)
        elif args.get("due"):
            rems = svc.list_due_reminders(user_id=user_id)
        else:
            rems = svc.list_reminders(user_id=user_id)
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
        raw_id = args.get("reminder_id") or args.get("id")
        user_id = args.get("user_id")
        if not raw_id:
            msg = args.get("message") or args.get("title")
            if msg:
                rems = svc.list_reminders(user_id=user_id)
                for r in rems:
                    if str(msg).lower() in r.message.lower():
                        raw_id = r.id
                        break
        if not raw_id:
            return {"success": False, "error": "reminder_id is required"}
        svc.delete_reminder(int(raw_id))
        record_activity(session, f"Reminder deleted: ID #{raw_id}", source="reminder", user_id=user_id)
        return {"success": True, "message": f"Reminder #{raw_id} deleted successfully.", "reminder_id": int(raw_id)}


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
        title = args.get("title") or args.get("name") or "Schedule Item"
        raw_start = args.get("starts_at") or args.get("start_time") or args.get("start")
        raw_end = args.get("ends_at") or args.get("end_time") or args.get("end")
        start_dt = None
        end_dt = None
        if raw_start:
            try:
                start_dt = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
            except Exception:
                pass
        if raw_end:
            try:
                end_dt = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
            except Exception:
                pass
        now = datetime.now(timezone.utc)
        if start_dt is None:
            start_dt = now
        if end_dt is None:
            from datetime import timedelta
            end_dt = start_dt + timedelta(hours=1)
        sched_user_id = args.get("user_id") or 1
        s_item = svc.create_schedule_item(
            ScheduleItemCreate(
                title=str(title).strip(),
                starts_at=start_dt,
                ends_at=end_dt,
                task_id=args.get("task_id"),
            ),
            user_id=sched_user_id,
        )
        record_activity(session, f"Schedule added: {s_item.title}", source="schedule", user_id=sched_user_id)
        return _to_dict(s_item)


class ListScheduleTool(BaseTool):
    name = "list_schedule"
    description = "List schedule items."
    scope = PermissionScope.READ
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        svc = ScheduleService(session)
        items = svc.list_schedule_items(user_id=args.get("user_id"))
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
        raw_id = args.get("item_id") or args.get("id") or args.get("schedule_id")
        user_id = args.get("user_id")
        if not raw_id:
            title = args.get("title") or args.get("name")
            if title:
                items = svc.list_schedule_items(user_id=user_id)
                for s in items:
                    if str(title).lower() in s.title.lower():
                        raw_id = s.id
                        break
        if not raw_id:
            return {"success": False, "error": "item_id is required"}
        svc.delete_schedule_item(int(raw_id))
        record_activity(session, f"Schedule item deleted: ID #{raw_id}", source="schedule", user_id=user_id)
        return {"success": True, "message": f"Schedule item #{raw_id} deleted successfully.", "item_id": int(raw_id)}


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
        notifs = svc.list_notifications(unread_only=args.get("unread_only", False), user_id=args.get("user_id"))
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
        record_activity(session, f"Notification marked read: ID #{args['notification_id']}", source="notification", user_id=args.get("user_id"))
        return _to_dict(notif)


# ---------------- CHAT HISTORY ----------------
class SearchChatHistoryTool(BaseTool):
    """Search through past conversation messages to retrieve previous discussions token-efficiently."""

    name = "search_chat_history"
    description = (
        "Search through past conversation messages to recall prior instructions, discussions, "
        "or answers token-efficiently. Returns matching message excerpts."
    )
    scope = PermissionScope.READ
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords or search term to look for in past conversations.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of excerpts to return (default: 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        query = args.get("query", "").strip()
        if not query:
            return {"success": False, "error": "Query string is required"}
        limit = min(max(int(args.get("limit", 5)), 1), 10)
        from app.storage.models import Message, Conversation
        q_pattern = f"%{query}%"
        q = (
            session.query(Message, Conversation.title)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Message.content.ilike(q_pattern))
        )
        user_id = args.get("user_id")
        if user_id is not None:
            q = q.filter(Conversation.user_id == user_id)
        matches = q.order_by(Message.created_at.desc()).limit(limit).all()
        results = []
        for m, conv_title in matches:
            title = conv_title or f"Chat #{m.conversation_id}"
            results.append({
                "conversation_id": m.conversation_id,
                "conversation_title": title,
                "role": m.role,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "snippet": m.content[:240] + ("..." if len(m.content) > 240 else "") if m.content else "",
            })
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
            "message": f"Found {len(results)} past chat message(s) matching '{query}'." if results else "No past messages found matching your query."
        }


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
        content = args.get("content") or args.get("fact") or args.get("information") or args.get("text") or ""
        cat_str = args.get("category", "preference")
        try:
            cat = MemoryCategory(cat_str)
        except Exception:
            cat = MemoryCategory.PREFERENCE
        mem_user_id = args.get("user_id") or 1
        mem = svc.create_memory(
            MemoryCreate(content=str(content).strip(), category=cat),
            user_id=mem_user_id,
        )
        record_activity(session, f"Memory saved: {str(content)[:40]}", source="memory", user_id=mem_user_id)
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
            user_id=args.get("user_id"),
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
            user_id=args.get("user_id"),
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
        raw_id = args.get("memory_id") or args.get("id")
        user_id = args.get("user_id")
        if not raw_id:
            raise ValueError("memory_id is required for update_memory")
        cat = None
        if args.get("category"):
            try:
                cat = MemoryCategory(args["category"])
            except Exception:
                pass
        mem = svc.update_memory(
            int(raw_id),
            MemoryUpdate(content=args.get("content"), category=cat),
        )
        record_activity(session, f"Memory updated: ID #{raw_id}", source="memory", user_id=user_id or mem.user_id)
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
        raw_id = args.get("memory_id") or args.get("id")
        user_id = args.get("user_id")
        if not raw_id:
            q = args.get("content") or args.get("query")
            if q:
                mems = svc.retrieve_relevant_memories(query=str(q), limit=1, user_id=user_id)
                if mems:
                    raw_id = mems[0].id
        if not raw_id:
            return {"success": False, "error": "memory_id is required"}
        if args.get("hard_delete"):
            svc.delete_memory(int(raw_id))
            record_activity(session, f"Memory deleted: ID #{raw_id}", source="memory", user_id=user_id)
            return {"success": True, "message": f"Memory #{raw_id} permanently deleted.", "memory_id": int(raw_id)}
        else:
            mem = svc.archive_memory(int(raw_id))
            record_activity(session, f"Memory archived: ID #{raw_id}", source="memory", user_id=user_id)
            res = _to_dict(mem)
            res["message"] = f"Memory #{raw_id} archived successfully."
            return res


def _get_user_file_service(args: dict[str, Any]) -> FileService:
    user_id = args.get("user_id")
    if user_id:
        from app.core.config import get_settings
        user_ws = get_settings().ensure_workspace_dir() / "users" / f"user_{user_id}" / "files"
        user_ws.mkdir(parents=True, exist_ok=True)
        return FileService(workspace_dir=user_ws)
    return FileService()


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
        svc = _get_user_file_service(args)
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
        svc = _get_user_file_service(args)
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
        svc = _get_user_file_service(args)
        result = svc.write_file(
            relative_path=args["path"],
            content=args["content"],
            overwrite=False,
        )
        record_activity(session, f"File created: {args['path']}", source="file", user_id=args.get("user_id"))
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
        svc = _get_user_file_service(args)
        target = svc.resolve_and_validate_path(args["path"])
        if not target.exists():
            from app.files.exceptions import FileNotFoundInWorkspaceError

            raise FileNotFoundInWorkspaceError(f"File '{args['path']}' not found in workspace.")
        res = svc.write_file(args["path"], args["content"], overwrite=True)
        record_activity(session, f"File updated: {args['path']}", source="file", user_id=args.get("user_id"))
        return _to_dict(res)


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
        svc = _get_user_file_service(args)
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
        svc = _get_user_file_service(args)
        svc.delete_file(relative_path=args["path"])
        record_activity(session, f"File deleted: {args['path']}", source="file", user_id=args.get("user_id"))
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
    registry.register(AssignTaskToProjectTool())

    registry.register(CreateHabitTool())
    registry.register(ListHabitsTool())
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
    registry.register(SearchChatHistoryTool())

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
