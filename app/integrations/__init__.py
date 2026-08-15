"""
External integration adapters — implemented in Phase 7.

Will contain: thin adapter classes for AI providers, search APIs,
calendar, and messaging integrations, each behind a small interface so
app.ai and app.scheduling don't depend on a specific vendor's SDK
directly. Credentials are read from app.core.config.Settings only —
never hard-coded.
"""
