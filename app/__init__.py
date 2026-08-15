"""
Personal Productivity Assistant — application package.

This package is organized by responsibility, not by layer:
- app.core          orchestration, config, events, permissions (the "spine")
- app.tasks         task/project domain logic (Phase 1)
- app.habits        habit tracking domain logic (Phase 2)
- app.scheduling    scheduling/reminders domain logic (Phase 2)
- app.planning      daily planning / prioritization logic (Phase 5)
- app.ai            LLM abstraction, tool-calling, conversation (Phase 4-5)
- app.storage       SQLAlchemy models, sessions, migrations (Phase 1-2)
- app.files         controlled assistant-workspace file tools (Phase 6)
- app.integrations  external API adapters (Phase 7)
- app.voice         STT/TTS (Phase 8)
- app.interfaces    FastAPI routes, web UI glue, CLI (Phase 3+)

Each subpackage is independently testable and should not import from
`app.interfaces` (interfaces depend on domain logic, never the reverse).
"""
