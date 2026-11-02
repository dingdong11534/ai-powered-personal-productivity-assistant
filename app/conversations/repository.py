"""Repository layer for Conversation and Message persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_conversation(self, title: str | None = None, user_id: int | None = None) -> Conversation:
        conv = Conversation(title=title, user_id=user_id)
        self.session.add(conv)
        self.session.commit()
        self.session.refresh(conv)
        return conv

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        return self.session.get(Conversation, conversation_id)

    def list_conversations(
        self, limit: int = 50, skip: int = 0, user_id: int | None = None
    ) -> list[Conversation]:
        stmt = select(Conversation).order_by(Conversation.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        stmt = stmt.offset(skip).limit(limit)
        return list(self.session.scalars(stmt).all())

    def delete_conversation(self, conversation_id: int) -> bool:
        conv = self.get_conversation(conversation_id)
        if not conv:
            return False
        self.session.delete(conv)
        self.session.commit()
        return True

    def create_message(
        self,
        conversation_id: int,
        role: str,
        content: str | None = None,
        tool_calls: str | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
        )
        self.session.add(msg)
        self.session.commit()
        self.session.refresh(msg)
        return msg

    def list_messages(self, conversation_id: int) -> list[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        return list(self.session.scalars(stmt).all())
