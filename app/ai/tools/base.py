"""Base tool class for controlled AI tool calls."""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.core.permissions import PermissionScope


class BaseTool(ABC):
    """Abstract base class for all tools accessible by the AI Assistant."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    scope: PermissionScope = PermissionScope.WRITE

    @abstractmethod
    def execute(self, args: dict[str, Any], session: Session) -> dict[str, Any]:
        """Execute the tool against domain services using the provided session."""
