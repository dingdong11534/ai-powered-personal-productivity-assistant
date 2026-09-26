"""FastAPI router for Conversations and AI Assistant chat interactions."""

import json

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.assistant import AssistantCore
from app.conversations.schemas import ConversationCreate, ConversationRead, MessageCreate, MessageRead
from app.conversations.service import ConversationService
from app.storage.database import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    session: Session = Depends(get_db),
) -> ConversationRead:
    """Create a new chat conversation session."""
    return ConversationService(session).create_conversation(data)


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    limit: int = 50,
    skip: int = 0,
    session: Session = Depends(get_db),
) -> list[ConversationRead]:
    """List chat conversations."""
    return ConversationService(session).list_conversations(limit=limit, skip=skip)


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: int,
    session: Session = Depends(get_db),
) -> ConversationRead:
    """Get conversation details."""
    return ConversationService(session).get_conversation(conversation_id)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_conversation(
    conversation_id: int,
    session: Session = Depends(get_db),
) -> Response:
    """Delete a conversation and its messages."""
    ConversationService(session).delete_conversation(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
def get_messages(
    conversation_id: int,
    session: Session = Depends(get_db),
) -> list[MessageRead]:
    """List all messages in a conversation transcript."""
    return ConversationService(session).get_messages(conversation_id)


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: int,
    data: MessageCreate,
    stream: bool = Query(default=False),
    session: Session = Depends(get_db),
):
    """Send a user message to the conversation and trigger the AI Assistant.

    If stream=True, returns an SSE text/event-stream StreamingResponse.
    Otherwise returns the saved MessageRead model with 201 Created status.
    """
    assistant = AssistantCore(session, destructive_authorized=data.authorize_destructive)
    user_text = data.content or ""

    if stream:
        def sse_generator():
            try:
                for event in assistant.handle_user_message_stream(conversation_id, user_text):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'event': 'error', 'error': str(exc)}, default=str)}\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return assistant.handle_user_message(conversation_id, user_text)
