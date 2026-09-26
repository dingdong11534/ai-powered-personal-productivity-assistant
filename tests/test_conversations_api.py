"""Tests for Conversations and Chat API endpoints."""

def test_conversations_api_flow(client):
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


def test_conversations_api_destructive_authorization_flow(client):
    # Create task first
    task_res = client.post("/tasks", json={"title": "Chat Delete Target Task"})
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # 1. Create conversation
    res_create = client.post("/conversations", json={"title": "Destructive Chat"})
    assert res_create.status_code == 201
    conv_id = res_create.json()["id"]

    # 2. Send delete request without authorization (defaults to false)
    res_unauth = client.post(
        f"/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Please delete task"},
    )
    assert res_unauth.status_code == 201

    # Verify task still exists in DB
    check_task = client.get(f"/tasks/{task_id}")
    assert check_task.status_code == 200

    # Transcript has tool failure with permission denied
    messages = client.get(f"/conversations/{conv_id}/messages").json()
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) >= 1
    assert "Permission denied" in tool_msgs[0]["content"]

    # 3. Send delete request WITH explicit authorization (authorize_destructive=true)
    res_auth = client.post(
        f"/conversations/{conv_id}/messages",
        json={
            "role": "user",
            "content": "Please delete task",
            "authorize_destructive": True,
        },
    )
    assert res_auth.status_code == 201

    # Verify task is now deleted
    check_task_deleted = client.get(f"/tasks/{task_id}")
    assert check_task_deleted.status_code == 404


def test_conversations_api_request_size_guardrail(client):
    # 1. Create conversation
    res_create = client.post("/conversations", json={"title": "Size Guardrail Test"})
    assert res_create.status_code == 201
    conv_id = res_create.json()["id"]

    # 2. Send oversized message (12,001 chars)
    oversized_content = "A" * 12_001
    res = client.post(
        f"/conversations/{conv_id}/messages",
        json={"role": "user", "content": oversized_content},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["role"] == "assistant"
    assert "Your message is too large to process" in body["content"]
    assert "12,001 characters" in body["content"]
