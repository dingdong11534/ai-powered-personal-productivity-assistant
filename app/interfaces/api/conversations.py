"""FastAPI router for Conversations and AI Assistant chat interactions."""

from fastapi import APIRouter, Depends, status
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


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    session: Session = Depends(get_db),
) -> None:
    """Delete a conversation and its messages."""
    ConversationService(session).delete_conversation(conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
def get_messages(
    conversation_id: int,
    session: Session = Depends(get_db),
) -> list[MessageRead]:
    """List all messages in a conversation transcript."""
    return ConversationService(session).get_messages(conversation_id)


@router.post("/{conversation_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: int,
    data: MessageCreate,
    session: Session = Depends(get_db),
) -> MessageRead:
    """Send a user message to the conversation and trigger the AI Assistant."""
    assistant = AssistantCore(session)
    user_text = data.content or ""
    return assistant.handle_user_message(conversation_id, user_text)
