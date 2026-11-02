import pytest
from app.ai.assistant import AssistantCore
from app.ai.tools.implementations import CreateTaskTool, DeleteTaskTool, UpdateTaskTool, CompleteTaskTool
from app.conversations.schemas import MessageCreate, MessageRead
from app.conversations.service import ConversationService
from app.tasks.service import TaskService
from datetime import datetime, timezone


def test_create_task_tool_resilience(db_session):
    tool = CreateTaskTool()
    
    # 1. Standard creation
    res1 = tool.execute({"title": "Test Task 1", "priority": 1}, db_session)
    assert res1["title"] == "Test Task 1"
    assert res1["priority"] == 1
    assert res1["id"] is not None

    # 2. String priority mapping ('critical' -> 1)
    res2 = tool.execute({"title": "Test Task 2", "priority": "critical"}, db_session)
    assert res2["title"] == "Test Task 2"
    assert res2["priority"] == 1

    # 3. Model passed 'name' instead of 'title'
    res3 = tool.execute({"name": "kunal", "priority": "highest"}, db_session)
    assert res3["title"] == "kunal"
    assert res3["priority"] == 1

    # 4. Model passed 'description' as task name
    res4 = tool.execute({"description": "Buy groceries", "priority": 3}, db_session)
    assert res4["title"] == "Buy groceries"
    assert res4["priority"] == 3


def test_update_and_complete_task_tool_resilience(db_session):
    create_tool = CreateTaskTool()
    created = create_tool.execute({"title": "Initial Task", "priority": 2}, db_session)
    task_id = created["id"]

    # Update with 'id' instead of 'task_id'
    update_tool = UpdateTaskTool()
    updated = update_tool.execute({"id": task_id, "title": "Updated Initial Task"}, db_session)
    assert updated["title"] == "Updated Initial Task"

    # Complete with 'id' instead of 'task_id'
    complete_tool = CompleteTaskTool()
    completed = complete_tool.execute({"id": task_id}, db_session)
    assert completed["status"] == "done"


def test_assistant_core_intent_extraction(db_session):
    core = AssistantCore(db_session)

    intent1 = core._extract_task_creation_intent("create a task name kunal with critical priority")
    assert intent1 is not None
    assert intent1["title"] == "kunal"
    assert intent1["priority"] == 1

    intent2 = core._extract_task_creation_intent("create a new task named kunal and set the priority to the highest")
    assert intent2 is not None
    assert intent2["title"] == "kunal"
    assert intent2["priority"] == 1

    intent3 = core._extract_task_creation_intent("add a task buy groceries")
    assert intent3 is not None
    assert intent3["title"] == "buy groceries"
    assert intent3["priority"] == 2

    intent4 = core._extract_task_creation_intent("make a todo finish report with high priority")
    assert intent4 is not None
    assert intent4["title"] == "finish report"
    assert intent4["priority"] == 2


def test_assistant_core_find_pending_task_creation(db_session):
    core = AssistantCore(db_session)
    
    # Simulate a conversation where assistant offered to create task
    msgs = [
        MessageRead(
            id=1,
            conversation_id=1,
            role="user",
            content="create a task named kunal",
            created_at=datetime.now(timezone.utc)
        ),
        MessageRead(
            id=2,
            conversation_id=1,
            role="assistant",
            content="Great, I will now create your new task titled \"kunal\".",
            created_at=datetime.now(timezone.utc)
        )
    ]

    pending = core._find_pending_task_creation(msgs, "do that")
    assert pending is not None
    assert pending["title"] == "kunal"
