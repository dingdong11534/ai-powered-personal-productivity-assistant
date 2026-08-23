"""Conversation management package.

Provides persistence and business logic for chat conversations and message
histories between the user and the AI Assistant.
"""

from app.conversations.exceptions import ConversationNotFoundError, MessageNotFoundError
from app.conversations.schemas import ConversationCreate, ConversationRead, MessageCreate, MessageRead
from app.conversations.service import ConversationService

__all__ = [
    "ConversationNotFoundError",
    "MessageNotFoundError",
    "ConversationCreate",
    "ConversationRead",
    "MessageCreate",
    "MessageRead",
    "ConversationService",
]
