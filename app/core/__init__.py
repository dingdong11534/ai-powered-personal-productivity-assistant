"""
Core: the parts every other subsystem depends on.

config.py       - typed application settings, loaded from environment/.env
events.py       - lightweight in-process publish/subscribe event bus
permissions.py  - permission model for gating sensitive/destructive actions
assistant.py    - AssistantCore, the orchestrator all interfaces call into

Nothing in app.core should import from app.tasks, app.ai, app.interfaces,
etc. Core is the dependency sink, not a dependency consumer — that's what
keeps it reusable from the web API, the CLI, and (later) voice, without
duplicating orchestration logic in each interface.
"""
