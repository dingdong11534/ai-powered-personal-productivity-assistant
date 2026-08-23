"""Tests for AssistantCore request flow and tool resolution loop."""

from app.ai.assistant import AssistantCore
from app.ai.provider import AIResponse, MockAIProvider, ToolCall
from app.conversations.schemas import ConversationCreate
from app.conversations.service import ConversationService
from app.tasks.service import TaskService


def test_assistant_core_text_response(db_session):
    conv_svc = ConversationService(db_session)
    conv = conv_svc.create_conversation(ConversationCreate(title="Text Chat"))

    provider = MockAIProvider(fixed_response=AIResponse(content="I am here to help!"))
    assistant = AssistantCore(db_session, provider=provider)

    msg = assistant.handle_user_message(conv.id, "Hello assistant")
    assert msg.role == "assistant"
    assert msg.content == "I am here to help!"

    messages = conv_svc.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


def test_assistant_core_tool_execution_flow(db_session):
    conv_svc = ConversationService(db_session)
    conv = conv_svc.create_conversation(ConversationCreate(title="Tool Chat"))

    # Mock provider first requests a tool call, then returns text after tool execution
    provider = MockAIProvider()
    assistant = AssistantCore(db_session, provider=provider)

    msg = assistant.handle_user_message(conv.id, "Please create task for testing assistant flow")
    assert msg.role == "assistant"

    # Verify task was created in DB
    tasks = TaskService(db_session).list_tasks()
    assert len(tasks) == 1
    assert tasks[0].title == "New AI Created Task"

    # Verify transcript contains user -> assistant (tool call) -> tool result -> final assistant response
    messages = conv_svc.get_messages(conv.id)
    assert len(messages) >= 4
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool" in roles
