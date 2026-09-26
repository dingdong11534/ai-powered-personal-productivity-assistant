"""
Phase 8 Tests: Streaming Assistant Responses (SSE)

Test suite covering:
1. Provider streaming (MockAIProvider and OpenAICompatibleProvider generate_stream)
2. AssistantCore streaming execution (handle_user_message_stream)
3. Mandatory tool status event emission during tool calls
4. Database persistence of the final assembled message and tool messages
5. Permission / authorization enforcement during streaming tool calls
6. SSE endpoint (POST /conversations/{id}/messages?stream=true) integration
7. Request size limits and error handling in streaming mode
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.ai.assistant import AssistantCore
from app.ai.provider import AIResponse, MockAIProvider, OpenAICompatibleProvider, ToolCall
from app.conversations.schemas import ConversationCreate
from app.conversations.service import ConversationService
from app.storage.database import Base


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


class TestProviderStreaming:
    def test_mock_provider_generate_stream_yields_deltas_and_response(self):
        provider = MockAIProvider(fixed_response=AIResponse(content="Hello world from mock"))
        stream = list(provider.generate_stream([{"role": "user", "content": "hi"}]))

        deltas = [item["content"] for item in stream if item["type"] == "delta"]
        assert len(deltas) > 0
        assert "".join(deltas).strip() == "Hello world from mock"

        final_item = [item for item in stream if item["type"] == "response"][0]
        assert final_item["response"].content == "Hello world from mock"

    def test_openai_provider_stream_parses_sse_chunks(self):
        provider = OpenAICompatibleProvider(base_url="https://api.mock.test/v1", api_key="test-key", model="mock-model")

        mock_sse_lines = [
            b'data: {"choices": [{"delta": {"content": "The "}}]}\n',
            b'data: {"choices": [{"delta": {"content": "weather "}}]}\n',
            b'data: {"choices": [{"delta": {"content": "is sunny."}}]}\n',
            b'data: [DONE]\n',
        ]

        mock_resp = MagicMock()
        mock_resp.__iter__.return_value = iter(mock_sse_lines)
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_resp):
            stream = list(provider.generate_stream([{"role": "user", "content": "weather"}]))

        deltas = [item["content"] for item in stream if item["type"] == "delta"]
        assert "".join(deltas) == "The weather is sunny."

        final_item = [item for item in stream if item["type"] == "response"][0]
        assert final_item["response"].content == "The weather is sunny."
        assert final_item["response"].tool_calls == []

    def test_openai_provider_stream_accumulates_tool_calls(self):
        provider = OpenAICompatibleProvider(base_url="https://api.mock.test/v1", api_key="test-key", model="mock-model")

        mock_sse_lines = [
            f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call_123', 'function': {'name': 'get_current_weather', 'arguments': '{\"loc'}}]}}]})}\n".encode("utf-8"),
            f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': 'ation\": \"London\"}'}}]}}]})}\n".encode("utf-8"),
            b"data: [DONE]\n",
        ]

        mock_resp = MagicMock()
        mock_resp.__iter__.return_value = iter(mock_sse_lines)
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_resp):
            stream = list(provider.generate_stream([{"role": "user", "content": "weather"}]))

        final_item = [item for item in stream if item["type"] == "response"][0]
        assert len(final_item["response"].tool_calls) == 1
        tc = final_item["response"].tool_calls[0]
        assert tc.id == "call_123"
        assert tc.name == "get_current_weather"
        assert tc.arguments == {"location": "London"}


class TestAssistantCoreStreaming:
    def test_streaming_plain_response_persists_to_db(self, in_memory_db):
        conv_svc = ConversationService(in_memory_db)
        conv = conv_svc.create_conversation(ConversationCreate(title="Test Convo"))

        provider = MockAIProvider(fixed_response=AIResponse(content="Plan for today: focus on tasks."))
        assistant = AssistantCore(in_memory_db, provider=provider)

        events = list(assistant.handle_user_message_stream(conv.id, "Give me a plan"))

        # Verify events emitted
        event_types = [e["event"] for e in events]
        assert "delta" in event_types
        assert "done" in event_types

        done_event = [e for e in events if e["event"] == "done"][0]
        assert done_event["message"]["content"] == "Plan for today: focus on tasks."

        # Verify DB persistence
        db_messages = conv_svc.get_messages(conv.id)
        assert len(db_messages) == 2
        assert db_messages[0].role == "user"
        assert db_messages[0].content == "Give me a plan"
        assert db_messages[1].role == "assistant"
        assert db_messages[1].content == "Plan for today: focus on tasks."

    def test_streaming_emits_status_for_tool_calls_and_executes(self, in_memory_db):
        conv_svc = ConversationService(in_memory_db)
        conv = conv_svc.create_conversation(ConversationCreate(title="Tool Convo"))

        mock_provider = MockAIProvider()  # "create task" triggers create_task tool in MockAIProvider
        assistant = AssistantCore(in_memory_db, provider=mock_provider)

        events = list(assistant.handle_user_message_stream(conv.id, "create task: Finish project"))

        # Confirm status event for tool call was emitted
        status_events = [e for e in events if e["event"] == "status"]
        assert len(status_events) == 1
        assert status_events[0]["stage"] == "tool_call"
        assert status_events[0]["name"] == "create_task"

        # Confirm done event was emitted
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) == 1

        # Confirm DB has user message, assistant tool request message, tool result message, and final assistant message
        db_messages = conv_svc.get_messages(conv.id)
        roles = [m.role for m in db_messages]
        assert roles == ["user", "assistant", "tool", "assistant"]


class TestConversationStreamingAPI:
    def test_api_stream_endpoint_returns_sse(self, client):
        # Create conversation
        create_resp = client.post("/conversations", json={"title": "SSE Test"})
        assert create_resp.status_code == 201
        convo_id = create_resp.json()["id"]

        # Post message with stream=true
        resp = client.post(
            f"/conversations/{convo_id}/messages?stream=true",
            json={"role": "user", "content": "Hello assistant"},
        )
        assert resp.status_code in (200, 201)
        assert "text/event-stream" in resp.headers["content-type"]

        # Parse SSE lines
        content = resp.text
        lines = [line.strip() for line in content.split("\n") if line.strip().startswith("data: ")]
        assert len(lines) > 0

        parsed_events = [json.loads(l[6:]) for l in lines]
        event_types = [e["event"] for e in parsed_events]
        assert "delta" in event_types
        assert "done" in event_types

        # Verify transcript endpoint returns saved messages
        get_resp = client.get(f"/conversations/{convo_id}/messages")
        assert get_resp.status_code == 200
        msgs = get_resp.json()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_api_non_streaming_endpoint_still_returns_json(self, client):
        create_resp = client.post("/conversations", json={"title": "Non-stream Test"})
        convo_id = create_resp.json()["id"]

        resp = client.post(
            f"/conversations/{convo_id}/messages",
            json={"role": "user", "content": "Hello sync"},
        )
        assert resp.status_code == 201
        assert "application/json" in resp.headers["content-type"]
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["content"] is not None

    def test_streaming_destructive_authorization_enforced(self, client):
        # Create a task to delete
        task_res = client.post("/tasks", json={"title": "Streaming Delete Task"})
        assert task_res.status_code == 201
        task_id = task_res.json()["id"]

        create_resp = client.post("/conversations", json={"title": "Auth Stream Test"})
        convo_id = create_resp.json()["id"]

        # 1. Unauthorized delete request over SSE
        resp_unauth = client.post(
            f"/conversations/{convo_id}/messages?stream=true",
            json={"role": "user", "content": "delete task", "authorize_destructive": False},
        )
        assert resp_unauth.status_code == 200
        # Task must still exist
        assert client.get(f"/tasks/{task_id}").status_code == 200

        # 2. Authorized delete request over SSE
        resp_auth = client.post(
            f"/conversations/{convo_id}/messages?stream=true",
            json={"role": "user", "content": "delete task", "authorize_destructive": True},
        )
        assert resp_auth.status_code == 200
        # Task must now be deleted
        assert client.get(f"/tasks/{task_id}").status_code == 404

    def test_streaming_message_size_guard_enforced(self, client):
        create_resp = client.post("/conversations", json={"title": "Size Guard Test"})
        convo_id = create_resp.json()["id"]

        giant_msg = "x" * 15_000
        resp = client.post(
            f"/conversations/{convo_id}/messages?stream=true",
            json={"role": "user", "content": giant_msg},
        )
        assert resp.status_code == 200
        lines = [line.strip() for line in resp.text.split("\n") if line.strip().startswith("data: ")]
        parsed = [json.loads(l[6:]) for l in lines]
        assert any("too large" in p.get("content", "") for p in parsed if p.get("event") == "delta")

    def test_streaming_interruption_preserves_db_records(self, in_memory_db):
        """Simulate client dropping connection mid-stream (reading only the first event).
        Server DB must still contain the user message."""
        conv_svc = ConversationService(in_memory_db)
        conv = conv_svc.create_conversation(ConversationCreate(title="Drop Stream Test"))

        provider = MockAIProvider(fixed_response=AIResponse(content="Full important reply."))
        assistant = AssistantCore(in_memory_db, provider=provider)

        gen = assistant.handle_user_message_stream(conv.id, "Hello before drop")
        # Client reads only first event then disconnects / stops iteration
        first_event = next(gen)
        assert first_event["event"] == "delta"

        # Check DB — user message was persisted immediately
        db_messages = conv_svc.get_messages(conv.id)
        assert any(m.role == "user" and m.content == "Hello before drop" for m in db_messages)
