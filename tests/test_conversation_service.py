"""Tests for Conversation and Message repository and service layer."""

import pytest
from app.conversations.exceptions import ConversationNotFoundError
from app.conversations.schemas import ConversationCreate, MessageCreate
from app.conversations.service import ConversationService
from app.storage.database import get_db


def test_conversation_crud(db_session):
    svc = ConversationService(db_session)

    # 1. Create conversation
    conv = svc.create_conversation(ConversationCreate(title="Test Chat"))
    assert conv.id is not None
    assert conv.title == "Test Chat"

    # 2. Get conversation
    fetched = svc.get_conversation(conv.id)
    assert fetched.id == conv.id
    assert fetched.title == "Test Chat"

    # 3. List conversations
    all_convs = svc.list_conversations()
    assert len(all_convs) >= 1
    assert any(c.id == conv.id for c in all_convs)

    # 4. Add messages
    m1 = svc.add_message(conv.id, MessageCreate(role="user", content="Hello assistant"))
    assert m1.id is not None
    assert m1.role == "user"
    assert m1.content == "Hello assistant"

    m2 = svc.add_message(conv.id, MessageCreate(role="assistant", content="Hello user!"))
    assert m2.id is not None
    assert m2.role == "assistant"

    messages = svc.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].content == "Hello assistant"
    assert messages[1].content == "Hello user!"

    # 5. Delete conversation
    svc.delete_conversation(conv.id)
    with pytest.raises(ConversationNotFoundError):
        svc.get_conversation(conv.id)
