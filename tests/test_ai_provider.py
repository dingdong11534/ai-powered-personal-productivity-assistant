from app.ai.provider import (
    AIResponse,
    MockAIProvider,
    OpenAICompatibleProvider,
    ToolCall,
    get_ai_provider,
)
from app.core.config import Settings



def test_mock_ai_provider_default_behavior():
    provider = MockAIProvider()
    response = provider.generate([{"role": "user", "content": "Hello!"}])
    assert isinstance(response, AIResponse)
    assert response.content is not None
    assert "Hello!" in response.content


def test_mock_ai_provider_keyword_triggers():
    provider = MockAIProvider()

    # Create task trigger
    res_task = provider.generate([{"role": "user", "content": "Please create task for grocery shopping"}])
    assert len(res_task.tool_calls) == 1
    assert res_task.tool_calls[0].name == "create_task"

    # Complete habit trigger
    res_habit = provider.generate([{"role": "user", "content": "I want to complete habit 1"}])
    assert len(res_habit.tool_calls) == 1
    assert res_habit.tool_calls[0].name == "complete_habit"


def test_mock_ai_provider_fixed_override():
    custom_res = AIResponse(content="Fixed custom output")
    provider = MockAIProvider(fixed_response=custom_res)
    res = provider.generate([{"role": "user", "content": "Any message"}])
    assert res.content == "Fixed custom output"


def test_get_ai_provider_factory():
    s_mock = Settings(ai_provider="mock")
    p_mock = get_ai_provider(s_mock)
    assert isinstance(p_mock, MockAIProvider)

    s_openai = Settings(ai_provider="openai", ai_api_key="test-key")
    p_openai = get_ai_provider(s_openai)
    assert isinstance(p_openai, OpenAICompatibleProvider)
    assert p_openai.api_key == "test-key"


def test_openai_compatible_provider_network_error(monkeypatch):
    import urllib.request
    from urllib.error import URLError

    def mock_urlopen(*args, **kwargs):
        raise URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OpenAICompatibleProvider(Settings(ai_provider="openai", ai_api_key="test-key"))
    resp = provider.generate([{"role": "user", "content": "Hello"}])
    assert isinstance(resp, AIResponse)
    assert "Error connecting to AI Provider" in resp.content
    assert "Connection refused" in resp.content


def test_openai_compatible_provider_response_parsing(monkeypatch):
    import json
    import io
    import urllib.request

    class MockHTTPResponse:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_json = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "create_task",
                                "arguments": "{\"title\": \"Test Task\"}"
                            }
                        }
                    ]
                }
            }
        ]
    }

    def mock_urlopen(*args, **kwargs):
        return MockHTTPResponse(json.dumps(mock_json))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OpenAICompatibleProvider(Settings(ai_provider="openai", ai_api_key="test-key"))
    resp = provider.generate([{"role": "user", "content": "Create task"}])
    assert isinstance(resp, AIResponse)
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].id == "call_123"
    assert resp.tool_calls[0].name == "create_task"
    assert resp.tool_calls[0].arguments == {"title": "Test Task"}

