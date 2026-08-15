"""
AssistantCore — the single orchestrator every interface calls into.

WHAT THIS DOES (eventually)
-----------------------------
Per the architecture diagram in the project spec:

    Web / Voice / CLI -> Assistant Core -> Intent/AI Layer -> Tool
    Selection -> Controlled Tools -> Productivity Engine / Files / APIs
    -> Database -> Result -> Assistant Response -> Web / Voice

AssistantCore is the thing that sits right after "Web / Voice / CLI" in
that diagram. Every interface (FastAPI routes in Phase 3, the AI chat loop
in Phase 4, voice in Phase 8) calls the *same* AssistantCore methods
instead of each reimplementing "how do I create a task" or "how do I run a
tool call". That's what makes it possible to add voice in Phase 8 without
duplicating logic: voice does STT, gets text, hands it to the same
AssistantCore.handle_message() the web chat already uses.

WHY THIS EXISTS NOW, IN PHASE 0, WITH NO REAL METHODS
---------------------------------------------------------
This file exists at this stage only to pin down *where* orchestration will
live and what it depends on (Settings, EventBus), so that Phase 1-3 code
is written against a stable seam from the start. Every public method below
is a stub that raises NotImplementedError — implementing them now would
mean building task management, AI tool-calling, and permission enforcement
all at once, which is exactly the "build the entire application in one
pass" the project explicitly rules out.

WHAT TO UNDERSTAND BEFORE THE NEXT PHASE
--------------------------------------------
- Dependency injection via the constructor: AssistantCore takes Settings
  and EventBus as arguments rather than importing get_settings() and a
  global bus internally. That's what lets tests construct an
  AssistantCore with a throwaway EventBus and no real database.
- Why this class has no domain logic (no SQL, no task-specific code):
  domain logic belongs in app.tasks / app.habits / etc. AssistantCore's
  job in later phases is to route requests to those modules and enforce
  cross-cutting policy (permissions, logging, events) around them — not
  to know how a task is stored.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.events import EventBus
from app.core.permissions import PermissionChecker


class AssistantCore:
    """The orchestrator all interfaces (web, AI, voice) call into.

    Phase 0: construction only. Methods are stubbed and documented with
    the phase that will implement them, so the intended contract is clear
    before there's code behind it.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus | None = None,
        permission_checker: PermissionChecker | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus or EventBus()
        self.permission_checker = permission_checker or PermissionChecker()

    def handle_message(self, text: str, *, actor: str = "web-ui") -> str:
        """Handle a natural-language message and return a response.

        Implemented in Phase 4, once app.ai defines an LLM abstraction and
        tool-calling contract for this method to route through.
        """
        raise NotImplementedError("AI message handling arrives in Phase 4.")

    def generate_daily_plan(self) -> None:
        """Produce a prioritized plan for the day from current tasks/habits.

        Implemented in Phase 5, once app.planning exists and app.tasks /
        app.habits have real data to plan over.
        """
        raise NotImplementedError("Daily planning arrives in Phase 5.")
