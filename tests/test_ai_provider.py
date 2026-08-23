"""Tests for AI Provider interface and mock implementation."""

from app.ai.provider import AIResponse, MockAIProvider, ToolCall, get_ai_provider
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
