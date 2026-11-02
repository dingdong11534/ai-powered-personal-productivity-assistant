"""
Application configuration.

WHAT THIS DOES
---------------
Defines a single, typed `Settings` object that every other module reads
configuration from. Values are loaded from environment variables (and, in
development, from a `.env` file), validated, and given sane defaults where
possible.

WHY IT EXISTS
-------------
Two reasons this is its own module instead of scattered `os.getenv()` calls:

1. Single source of truth. Every setting (database URL, log level, AI
   provider keys, workspace path) is declared once, with a type and a
   default. If a required setting is missing or malformed, the app fails
   fast at startup instead of raising a confusing error three layers deep
   when a task is created.
2. Testability. Tests can construct a `Settings` instance directly with
   overrides, instead of monkeypatching environment variables.

DESIGN DECISION: pydantic-settings
-----------------------------------
`pydantic-settings` is used instead of a hand-rolled dataclass + os.environ
loader. This is a deliberate choice, not a "because it's popular" one: this
project already depends on pydantic for FastAPI's request/response models,
so pydantic-settings adds no new dependency family, and it gives us
validation (e.g. rejecting an invalid LOG_LEVEL) for free. If that stops
being true later (e.g. FastAPI is dropped), this module is the only place
that needs to change.

HOW DATA FLOWS
---------------
Process start -> Settings() is constructed once (see get_settings()) ->
reads OS environment, falling back to a `.env` file in the project root ->
validates each field -> other modules call get_settings() and receive the
same cached instance every time (see functools.lru_cache below).

WHAT TO UNDERSTAND BEFORE MOVING ON
-------------------------------------
- The difference between configuration (how the app behaves) and secrets
  (credentials). Both live here for now, but secrets must never be
  committed — see .env.example and .gitignore.
- Why `get_settings()` is cached: constructing Settings repeatedly would
  re-read and re-validate the environment on every call, which is wasteful
  and can also mask bugs where a value was mutated at runtime and nothing
  bothered to reload it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (app/core/config.py -> app -> root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Typed, validated application configuration.

    Every field has a description because in a learning-oriented project
    the *reason* a setting exists matters as much as its value.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_name: str = Field(default="Personal Productivity Assistant")
    environment: Literal["development", "test", "production"] = Field(
        default="development",
        description="Controls things like debug logging and DB defaults.",
    )
    debug: bool = Field(default=True)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # --- Storage ---
    data_dir: Path = Field(
        default=PROJECT_ROOT / "data",
        description="Root directory for the SQLite DB and file workspace.",
    )
    workspace_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "workspace",
        description="Sandboxed directory for assistant workspace file access.",
    )
    max_file_read_bytes: int = Field(default=1_000_000, ge=1)
    max_file_write_bytes: int = Field(default=1_000_000, ge=1)
    max_file_results: int = Field(default=100, ge=1)
    max_file_scan_entries: int = Field(default=1_000, ge=1)
    max_workspace_depth: int = Field(default=10, ge=1)
    database_url: str = Field(
        default=f"sqlite:///{PROJECT_ROOT / 'data' / 'assistant.db'}",
        description="SQLAlchemy connection string. Defaults to an "
        "absolute path under the project's data/ directory (not a "
        "cwd-relative one) so it resolves the same way regardless of "
        "where `uvicorn` or `pytest` is invoked from. SQLite for "
        "local-first use; kept swappable via this single value.",
    )

    # --- AI layer ---
    ai_mode: str = Field(
        default="online",
        description="Current AI operating mode: 'online' (cloud API like Groq), 'offline' (local like Ollama), or 'mock'.",
    )
    ai_provider: str = Field(
        default="groq",
        description="Which AI backend adapter to use, e.g. 'mock', 'openai', "
        "'anthropic', 'groq', 'ollama'. 'mock' uses the local mock adapter.",
    )
    ai_api_key: str | None = Field(default=None, repr=False)
    ai_model: str = Field(
        default="qwen/qwen3.8-27b",
        description="Model name to pass to the AI provider.",
    )
    ai_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Base URL for OpenAI-compatible endpoint (e.g. Ollama or vLLM or Groq).",
    )

    # Dedicated Online (Cloud API) configuration
    online_ai_provider: str = Field(default="groq")
    online_ai_model: str = Field(default="qwen/qwen3.8-27b")
    online_ai_base_url: str = Field(default="https://api.groq.com/openai/v1")
    online_ai_api_key: str | None = Field(default=None, repr=False)

    # Dedicated Offline (Local LLM) configuration
    offline_ai_provider: str = Field(default="ollama")
    offline_ai_model: str = Field(default="qwen2.5:1.5b")
    offline_ai_base_url: str = Field(default="http://localhost:11434/v1")
    offline_ai_api_key: str | None = Field(default="ollama", repr=False)

    # Provider-specific configurations
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str = Field(default="https://api.openai.com/v1")

    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_model: str = Field(default="gemini-1.5-flash")
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta/openai/")

    groq_api_key: str | None = Field(default=None, repr=False)
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")

    grok_api_key: str | None = Field(default=None, repr=False)
    grok_model: str = Field(default="grok-beta")
    grok_base_url: str = Field(default="https://api.x.ai/v1")

    # --- External integrations (Phase 7) ---
    # Domain allowlist: exact hostnames the SSRF-safe client is permitted to reach.
    # Add entries here (or via EXTERNAL_ALLOWED_DOMAINS env var as comma-separated
    # list) before registering any tool that makes external network requests.
    external_allowed_domains: list[str] = Field(
        default=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
        description="Exact hostnames the ExternalHttpClient is permitted to contact.",
    )
    external_request_timeout_seconds: int = Field(
        default=10,
        ge=1,
        description="Maximum seconds to wait for an external HTTP response.",
    )
    external_max_response_bytes: int = Field(
        default=1_000_000,
        ge=1,
        description="Maximum response body size in bytes from an external request.",
    )

    def ensure_data_dir(self) -> Path:
        """Create the data directory if it doesn't exist yet, return it.

        Called explicitly (not at import time) so importing this module
        never has a filesystem side effect — only using it does.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def ensure_workspace_dir(self) -> Path:
        """Create the sandboxed workspace directory if it doesn't exist yet, return it."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return self.workspace_dir



@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance (constructed once).

    lru_cache with no arguments memoizes on the (empty) argument list, so
    the first call builds Settings and every later call returns the same
    object. Tests that need different settings should construct
    `Settings(...)` directly rather than calling this function.
    """
    return Settings()
