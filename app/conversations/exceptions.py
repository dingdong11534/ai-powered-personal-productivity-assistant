"""Exceptions for conversation management."""


class ConversationError(Exception):
    """Base exception for conversation package."""


class ConversationNotFoundError(ConversationError):
    """Raised when a requested conversation ID does not exist."""

    def __init__(self, conversation_id: int):
        super().__init__(f"Conversation {conversation_id} not found")
        self.conversation_id = conversation_id


class MessageNotFoundError(ConversationError):
    """Raised when a requested message ID does not exist."""

    def __init__(self, message_id: int):
        super().__init__(f"Message {message_id} not found")
        self.message_id = message_id
