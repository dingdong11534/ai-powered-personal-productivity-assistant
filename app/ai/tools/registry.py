import re
from typing import Any

from sqlalchemy.orm import Session

from app.ai.tools.base import BaseTool
from app.core.permissions import PermissionChecker, PermissionDenied, PermissionRequest


class ToolRegistry:
    """Registry maintaining available tools and enforcing permission policies."""

    def __init__(self, permission_checker: PermissionChecker | None = None):
        self._tools: dict[str, BaseTool] = {}
        self.permission_checker = permission_checker or PermissionChecker()

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_tools_schema(self, query: str | None = None, is_local: bool = False) -> list[dict[str, Any]]:
        """Format registered tools into OpenAI tool schema format, optionally filtering for local efficiency."""
        tools = list(self._tools.values())
        if is_local and query:
            q = query.lower()
            matched_names = set()

            # Domain keyword and ID mapping
            if any(w in q for w in ("task", "todo", "priority", "deadline", "status", "complete", "add", "create", "make", "new", "kunal", "connect", "assign")):
                matched_names.update(["create_task", "update_task", "delete_task", "list_tasks", "search_tasks", "complete_task", "assign_task_to_project"])
            if any(w in q for w in ("project", "workspace project", "connect", "assign")):
                matched_names.update(["create_project", "update_project", "archive_project", "delete_project", "list_projects", "assign_task_to_project"])
            if any(w in q for w in ("habit", "streak", "routine")):
                matched_names.update(["create_habit", "update_habit", "complete_habit", "delete_habit", "list_habits"])
            if any(w in q for w in ("pomodoro", "pomo", "focus", "timer")):
                matched_names.update(["start_pomodoro", "end_pomodoro", "delete_pomodoro_session"])
            if any(w in q for w in ("remind", "reminder", "alert")):
                matched_names.update(["create_reminder", "delete_reminder", "list_reminders"])
            if any(w in q for w in ("schedule", "calendar", "event", "meeting", "block", "slot")):
                matched_names.update(["create_schedule_item", "delete_schedule_item", "list_schedule"])
            if any(w in q for w in ("memory", "remember", "preference", "forget", "recall")):
                matched_names.update(["remember_information", "delete_memory", "list_memories", "search_memories"])
            if any(w in q for w in ("file", "document", "notes.txt", "notes", "write file", "read file", "list file")):
                matched_names.update(["create_workspace_file", "read_workspace_file", "list_workspace_files", "delete_workspace_file"])
            if any(w in q for w in ("delete", "remove", "destroy", "erase", "yes", "confirm", "proceed", "authorize", "do that", "go ahead")):
                matched_names.update([
                    "create_task",
                    "delete_task",
                    "delete_project",
                    "delete_habit",
                    "delete_pomodoro_session",
                    "delete_reminder",
                    "delete_schedule_item",
                    "delete_memory",
                    "delete_workspace_file",
                ])
            if any(w in q for w in ("weather", "temperature", "forecast", "rain", "sunny", "humid", "wind", "degrees")):
                matched_names.update(["get_current_weather"])

            if matched_names:
                tools = [t for t in tools if t.name in matched_names]
            else:
                # Fallback core tool set for local models so small contexts aren't flooded with 30 schemas
                core_tools = {"create_task", "update_task", "delete_task", "list_tasks", "search_tasks", "list_projects", "create_reminder", "list_reminders", "get_current_weather"}
                tools = [t for t in tools if t.name in core_tools]

        schemas = []
        for tool in tools:
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            })
        return schemas

    def execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        session: Session,
        *,
        destructive_authorized: bool = False,
    ) -> dict[str, Any]:
        """Validate permissions and execute the tool safely.

        Returns a structured dictionary with success flag and data/error message.
        """
        tool = self.get_tool(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' is not registered."}

        # Permission check
        try:
            req = PermissionRequest(
                scope=tool.scope,
                actor="ai",
                description=f"Tool call '{tool.name}' with args {args}",
                # This value comes from the trusted interface request, never
                # from model-generated tool arguments.
                authorized=destructive_authorized,
            )
            self.permission_checker.check(req)
        except PermissionDenied as p_err:
            return {"success": False, "error": f"Permission denied: {str(p_err)}"}

        # Execute tool
        try:
            result = tool.execute(args, session)
            return {"success": True, "data": result}
        except Exception as err:
            return {"success": False, "error": str(err)}
