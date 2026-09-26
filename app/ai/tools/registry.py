"""Tool registry and safe tool execution orchestrator."""

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

            # Domain keyword mapping
            if any(w in q for w in ("task", "todo", "priority", "deadline", "status", "complete")):
                matched_names.update(["create_task", "update_task", "delete_task", "list_tasks", "get_task"])
            if any(w in q for w in ("project", "workspace project")):
                matched_names.update(["create_project", "update_project", "archive_project", "delete_project", "list_projects"])
            if any(w in q for w in ("habit", "streak", "routine")):
                matched_names.update(["create_habit", "update_habit", "complete_habit", "delete_habit", "list_habits"])
            if any(w in q for w in ("pomodoro", "pomo", "focus", "timer")):
                matched_names.update(["start_pomodoro", "end_pomodoro", "delete_pomodoro_session", "list_pomodoro_sessions"])
            if any(w in q for w in ("remind", "reminder", "alert")):
                matched_names.update(["create_reminder", "delete_reminder", "list_reminders"])
            if any(w in q for w in ("schedule", "calendar", "event", "meeting", "block", "slot")):
                matched_names.update(["create_schedule_item", "update_schedule_item", "delete_schedule_item", "list_schedule_items"])
            if any(w in q for w in ("memory", "remember", "preference", "forget", "recall")):
                matched_names.update(["remember_information", "delete_memory", "list_memories"])
            if any(w in q for w in ("file", "document", "notes.txt", "notes", "write file", "read file", "list file")):
                matched_names.update(["create_workspace_file", "read_workspace_file", "list_workspace_files", "delete_workspace_file"])
            if any(w in q for w in ("delete", "remove", "destroy", "erase")):
                matched_names.update([
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
