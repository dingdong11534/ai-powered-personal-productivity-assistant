"""FastAPI router for AI mode configuration and status."""

from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.provider import (
    get_ai_status,
    set_ai_configuration,
    set_current_ai_mode,
    test_ai_provider_connection,
    test_all_ai_providers,
)
from app.core.auth import get_current_user
from app.storage.database import get_db
from app.storage.models import User
from app.users.service import UserService

router = APIRouter(prefix="/ai", tags=["ai"])


class AIModeUpdateRequest(BaseModel):
    mode: str = Field(
        ...,
        description="Target mode: 'online' (Cloud API) or 'offline' (Local LLM / Ollama)",
        examples=["online", "offline"],
    )


class AIConfigUpdateRequest(BaseModel):
    provider: str = Field(
        ...,
        description="Provider identifier: 'openai', 'gemini', 'groq', 'grok', 'offline', 'mock'",
        examples=["openai", "gemini", "groq", "grok", "offline"],
    )
    model: str | None = Field(default=None, description="Optional custom model name")
    api_key: str | None = Field(default=None, description="Optional API key for provider")
    base_url: str | None = Field(default=None, description="Optional base URL endpoint")
    persist: bool = Field(default=True, description="Persist changes to .env file")


class AIConnectionTestRequest(BaseModel):
    provider: str = Field(default="openai", description="Provider to test")
    model: str | None = Field(default=None, description="Model to test")
    api_key: str | None = Field(default=None, description="API key to test")
    base_url: str | None = Field(default=None, description="Base URL to test")


class UserAPIKeyUpdateRequest(BaseModel):
    provider: str = Field(..., description="Provider name e.g. 'openai', 'gemini', 'groq', 'grok'")
    api_key: str | None = Field(default=None, description="Custom API key. Provide empty string or null to remove and revert to system default.")


@router.get("/status", response_model=dict[str, Any])
@router.get("/mode", response_model=dict[str, Any])
def get_status(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get active AI provider mode, active model, and all available provider presets for current user."""
    return get_ai_status(user=current_user)


@router.get("/user-keys", response_model=dict[str, Any])
def get_user_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get the current user's custom API key overrides."""
    svc = UserService(db)
    keys = svc.get_custom_api_keys(current_user.id)
    masked = {}
    for prov, k in keys.items():
        if k and len(k) > 8:
            masked[prov] = f"{k[:4]}...{k[-4:]}"
        else:
            masked[prov] = "****"
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "custom_keys": masked,
        "configured_providers": list(keys.keys()),
        "status": get_ai_status(user=current_user),
    }


@router.post("/user-keys", response_model=dict[str, Any])
def set_user_key(
    data: UserAPIKeyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Set or delete a custom API key for the current user.
    
    If api_key is provided and non-empty, sets custom key for that provider.
    If empty or null, removes the custom key so the user uses the default system key.
    """
    svc = UserService(db)
    updated = svc.update_custom_api_key(current_user.id, data.provider, data.api_key)
    refreshed_user = svc.get_by_id(current_user.id)
    return {
        "status": "ok",
        "provider": data.provider.lower(),
        "has_custom_key": data.provider.lower() in updated,
        "ai_status": get_ai_status(user=refreshed_user),
    }


@router.post("/mode", response_model=dict[str, Any])
def update_mode(data: AIModeUpdateRequest) -> dict[str, Any]:
    """Switch active AI mode between online (cloud API) and offline (local Ollama)."""
    return set_current_ai_mode(data.mode)


@router.post("/config", response_model=dict[str, Any])
def update_configuration(data: AIConfigUpdateRequest) -> dict[str, Any]:
    """Configure and activate an AI provider (e.g. OpenAI, Gemini, Groq, Grok, or Offline)."""
    return set_ai_configuration(
        provider=data.provider,
        model=data.model,
        api_key=data.api_key,
        base_url=data.base_url,
        persist=data.persist,
    )


@router.post("/test", response_model=dict[str, Any])
def test_connection(
    data: AIConnectionTestRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Test connectivity and credentials for an AI provider."""
    return test_ai_provider_connection(
        provider=data.provider,
        model=data.model,
        api_key=data.api_key,
        base_url=data.base_url,
        user=current_user,
    )


@router.get("/test-all", response_model=dict[str, Any])
@router.post("/test-all", response_model=dict[str, Any])
def test_all_connections(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Test connectivity and status across all available AI models and providers."""
    return test_all_ai_providers(user=current_user)

