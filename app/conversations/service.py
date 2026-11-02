"""Service layer for conversation and message management."""

from typing import Any

from sqlalchemy.orm import Session

from app.conversations.exceptions import ConversationNotFoundError
from app.conversations.repository import ConversationRepository
from app.conversations.schemas import ConversationCreate, ConversationRead, MessageCreate, MessageRead


class ConversationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = ConversationRepository(session)

    def create_conversation(
        self, data: ConversationCreate, user_id: int | None = None
    ) -> ConversationRead:
        conv = self.repo.create_conversation(title=data.title, user_id=user_id)
        return ConversationRead.model_validate(conv)

    def get_conversation(self, conversation_id: int) -> ConversationRead:
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            raise ConversationNotFoundError(conversation_id)
        return ConversationRead.model_validate(conv)

    def list_conversations(
        self, limit: int = 50, skip: int = 0, user_id: int | None = None
    ) -> list[ConversationRead]:
        convs = self.repo.list_conversations(limit=limit, skip=skip, user_id=user_id)
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
        self._append_to_chat_history_file(conv, msg)
        return MessageRead.model_validate(msg)

    def _append_to_chat_history_file(self, conv: Any, msg: Any) -> None:
        """Maintain a compact, token-efficient workspace file of recent conversation turns."""
        try:
            from app.core.config import get_settings

            ws_dir = get_settings().ensure_workspace_dir()
            hist_file = ws_dir / "chat_history.txt"

            clean_content = (msg.content or "").strip().replace("\n", " ")
            if not clean_content:
                return
            if len(clean_content) > 280:
                clean_content = clean_content[:280] + "..."

            title = getattr(conv, "title", None) or f"Chat #{getattr(conv, 'id', '?')}"
            line = f"[{title}] {msg.role.upper()}: {clean_content}\n"

            # 1. Shared chat history file
            existing_lines: list[str] = []
            if hist_file.exists():
                existing_lines = hist_file.read_text(encoding="utf-8").splitlines(keepends=True)
            existing_lines.append(line)
            if len(existing_lines) > 200:
                existing_lines = existing_lines[-200:]
            hist_file.write_text("".join(existing_lines), encoding="utf-8")

            # 2. Per-user chat history file
            user_id = getattr(conv, "user_id", None)
            if user_id:
                u_dir = ws_dir / "users" / f"user_{user_id}"
                u_dir.mkdir(parents=True, exist_ok=True)
                u_hist = u_dir / "chat_history.txt"
                u_lines: list[str] = []
                if u_hist.exists():
                    u_lines = u_hist.read_text(encoding="utf-8").splitlines(keepends=True)
                u_lines.append(line)
                if len(u_lines) > 200:
                    u_lines = u_lines[-200:]
                u_hist.write_text("".join(u_lines), encoding="utf-8")
        except Exception:
            pass

    def get_messages(self, conversation_id: int) -> list[MessageRead]:
        conv = self.repo.get_conversation(conversation_id)
        if not conv:
            raise ConversationNotFoundError(conversation_id)
        msgs = self.repo.list_messages(conversation_id)
        return [MessageRead.model_validate(m) for m in msgs]
