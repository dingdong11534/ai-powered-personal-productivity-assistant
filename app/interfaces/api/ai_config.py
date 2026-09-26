"""FastAPI router for AI mode configuration and status."""

from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.ai.provider import get_ai_status, set_current_ai_mode

router = APIRouter(prefix="/ai", tags=["ai"])


class AIModeUpdateRequest(BaseModel):
    mode: str = Field(
        ...,
        description="Target mode: 'online' (Cloud API) or 'offline' (Local LLM / Ollama)",
        examples=["online", "offline"],
    )


@router.get("/status", response_model=dict[str, Any])
@router.get("/mode", response_model=dict[str, Any])
def get_status() -> dict[str, Any]:
    """Get active AI provider mode and model details."""
    return get_ai_status()


@router.post("/mode", response_model=dict[str, Any])
def update_mode(data: AIModeUpdateRequest) -> dict[str, Any]:
    """Switch active AI mode between online (cloud API) and offline (local Ollama)."""
    return set_current_ai_mode(data.mode)
