"""Tests for Conversations and Chat API endpoints."""

from fastapi.testclient import TestClient
from app.interfaces.main import app

client = TestClient(app)


def test_conversations_api_flow():
    # 1. Create conversation
    res_create = client.post("/conversations", json={"title": "API Chat"})
    assert res_create.status_code == 201
    conv_data = res_create.json()
    conv_id = conv_data["id"]
    assert conv_data["title"] == "API Chat"

    # 2. Get conversation
    res_get = client.get(f"/conversations/{conv_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == conv_id

    # 3. List conversations
    res_list = client.get("/conversations")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 4. Send message
    res_msg = client.post(
        f"/conversations/{conv_id}/messages",
        json={"role": "user", "content": "What should I work on today?"},
    )
    assert res_msg.status_code == 201
    assistant_msg = res_msg.json()
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] is not None

    # 5. Get message transcript
    res_transcript = client.get(f"/conversations/{conv_id}/messages")
    assert res_transcript.status_code == 200
    messages = res_transcript.json()
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"

    # 6. Delete conversation
    res_del = client.delete(f"/conversations/{conv_id}")
    assert res_del.status_code == 204
