"""Service layer for conversation and message management."""

from sqlalchemy.orm import Session

from app.conversations.exceptions import ConversationNotFoundError
from app.conversations.repository import ConversationRepository
from app.conversations.schemas import ConversationCreate, ConversationRead, MessageCreate, MessageRead


class ConversationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = ConversationRepository(session)

    def create_conversation(self, data: ConversationCreate) -> ConversationRead:
        conv = self.repo.create_conversation(title=data.title)
        return ConversationRead.model_validate(conv)

    def get_conversation(self, conversation_id: int) -> ConversationRead:
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            raise ConversationNotFoundError(conversation_id)
        return ConversationRead.model_validate(conv)

    def list_conversations(self, limit: int = 50, skip: int = 0) -> list[ConversationRead]:
        convs = self.repo.list_conversations(limit=limit, skip=skip)
        return [ConversationRead.model_validate(c) for c in convs]

    def delete_conversation(self, conversation_id: int) -> None:
        if not self.repo.delete_conversation(conversation_id):
            raise ConversationNotFoundError(conversation_id)

    def add_message(self, conversation_id: int, data: MessageCreate) -> MessageRead:
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            raise ConversationNotFoundError(conversation_id)
        msg = self.repo.create_message(
            conversation_id=conversation_id,
            role=data.role,
            content=data.content,
            tool_calls=data.tool_calls,
            tool_call_id=data.tool_call_id,
            name=data.name,
        )
        return MessageRead.model_validate(msg)

    def get_messages(self, conversation_id: int) -> list[MessageRead]:
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            raise ConversationNotFoundError(conversation_id)
        msgs = self.repo.list_messages(conversation_id)
        return [MessageRead.model_validate(m) for m in msgs]
