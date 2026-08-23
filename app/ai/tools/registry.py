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

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Format registered tools into OpenAI tool schema format."""
        schemas = []
        for tool in self._tools.values():
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
