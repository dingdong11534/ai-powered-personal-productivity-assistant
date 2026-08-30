"""
AssistantCore — the single orchestrator every interface calls into.

Per the architecture specification:
    Web / Voice / CLI -> Assistant Core -> AI Layer / Tools -> Domain Services

This module re-exports the canonical `AssistantCore` implemented in `app.ai.assistant`
so that any interface (Web API, Voice, CLI) can import `AssistantCore` from `app.core.assistant`.
"""

from app.ai.assistant import AssistantCore

__all__ = ["AssistantCore"]

