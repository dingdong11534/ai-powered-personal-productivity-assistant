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


def test_assistant_core_destructive_two_step_flow(db_session):
    conv_svc = ConversationService(db_session)
    task_svc = TaskService(db_session)

    # 1. Create a task in DB
    from app.tasks.schemas import TaskCreate
    task = task_svc.create_task(TaskCreate(title="Target Task to Delete"))
    task_id = task.id

    conv = conv_svc.create_conversation(ConversationCreate(title="Destructive Assistant Chat"))

    # Step 1: User requests delete, destructive_authorized is False
    provider = MockAIProvider()
    assistant_unauth = AssistantCore(db_session, provider=provider, destructive_authorized=False)
    msg1 = assistant_unauth.handle_user_message(conv.id, "delete task")
    assert msg1.role == "assistant"

    # Task is NOT deleted
    assert task_svc.get_task(task_id) is not None

    # Step 2: User confirms deletion, destructive_authorized is True
    assistant_auth = AssistantCore(db_session, provider=provider, destructive_authorized=True)
    msg2 = assistant_auth.handle_user_message(conv.id, "delete task")
    assert msg2.role == "assistant"

    # Task is now deleted
    from app.tasks.exceptions import TaskNotFoundError
    import pytest
    with pytest.raises(TaskNotFoundError):
        task_svc.get_task(task_id)
