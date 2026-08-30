"""End-to-end integration test for AI Assistant and tool-calling system."""

from fastapi.testclient import TestClient
from app.interfaces.main import app

client = TestClient(app)


def test_e2e_ai_chat_and_tool_execution(db_session):
    # 1. Create a conversation
    resp = client.post("/conversations", json={"title": "E2E Integration Test Chat"})
    assert resp.status_code == 201
    conv = resp.json()
    conv_id = conv["id"]

    # 2. Post a user message that triggers tool execution (create_task)
    user_msg_resp = client.post(
        f"/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Please create task for testing assistant flow"},
    )
    assert user_msg_resp.status_code == 201
    asst_msg = user_msg_resp.json()
    assert asst_msg["role"] == "assistant"
    assert "Successfully executed tool" in asst_msg["content"]

    # 3. Verify that the task was actually created in the database via the /tasks endpoint
    tasks_resp = client.get("/tasks")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()
    assert len(tasks) >= 1
    created_task = next(t for t in tasks if t["title"] == "New AI Created Task")
    assert created_task["priority"] == 2
    assert created_task["status"] == "todo"

    # 4. Verify conversation transcript history contains all stages of tool execution
    messages_resp = client.get(f"/conversations/{conv_id}/messages")
    assert messages_resp.status_code == 200
    messages = messages_resp.json()

    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool" in roles
    assert len(messages) >= 4

    # 5. Send a plain text message (no tool trigger) and verify direct text response
    chat_resp = client.post(
        f"/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Thank you for creating the task!"},
    )
    assert chat_resp.status_code == 201
    chat_asst_msg = chat_resp.json()
    assert chat_asst_msg["role"] == "assistant"
    assert "Hello! I am your AI assistant" in chat_asst_msg["content"]
