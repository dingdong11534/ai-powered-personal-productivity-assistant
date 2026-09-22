"""AI Provider abstraction layer.

Defines a vendor-agnostic interface for text generation and tool calling.
Provides a MockAIProvider for offline testing and an OpenAICompatibleProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json

from typing import Any
import urllib.error
import urllib.request

from app.core.config import Settings, get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AIResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class AIProvider(ABC):
    """Abstract interface for AI model providers."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AIResponse:
        """Generate text or tool calls from a message transcript."""


class MockAIProvider(AIProvider):
    """Deterministic, configurable mock provider for testing and offline use."""

    def __init__(self, fixed_response: AIResponse | None = None):
        self.fixed_response = fixed_response
        self.history_called: list[list[dict[str, Any]]] = []

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AIResponse:
        self.history_called.append(messages)
        if self.fixed_response is not None:
            return self.fixed_response

        # Look at latest user message to produce realistic mock behaviors
        last_msg = messages[-1] if messages else {}
        user_text = (last_msg.get("content") or "").lower()

        # If previous message was a tool result, generate final assistant answer summarizing it
        if last_msg.get("role") == "tool":
            tool_name = last_msg.get("name", "tool")
            content = last_msg.get("content", "")
            return AIResponse(
                content=f"Successfully executed tool '{tool_name}'. Result: {content}"
            )

        # Keyword based tool trigger rules for mock provider
        if "create task" in user_text or "add task" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_task_1",
                        name="create_task",
                        arguments={"title": "New AI Created Task", "priority": 2},
                    )
                ],
            )

        if "complete habit" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_habit_1",
                        name="complete_habit",
                        arguments={"habit_id": 1},
                    )
                ],
            )

        if "remember that" in user_text or "please remember" in user_text or "remember:" in user_text:
            content_val = last_msg.get("content", "")
            if "remember that" in content_val.lower():
                content_val = content_val.lower().split("remember that", 1)[1].strip(" .")
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_mem_1",
                        name="remember_information",
                        arguments={"content": content_val or "I prefer focused work in the evening", "category": "preference"},
                    )
                ],
            )

        if "what do you remember" in user_text or "list memories" in user_text or "all memories" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_mem_list",
                        name="list_memories",
                        arguments={},
                    )
                ],
            )

        if "forget" in user_text or "delete memory" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_mem_del",
                        name="delete_memory",
                        arguments={"memory_id": 1},
                    )
                ],
            )

        if "write file" in user_text or "create file" in user_text or "save file" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_file_write",
                        name="create_workspace_file",
                        arguments={"path": "notes.txt", "content": "Assistant workspace note content"},
                    )
                ],
            )

        if "list workspace files" in user_text or "list files" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_file_list",
                        name="list_workspace_files",
                        arguments={"sub_path": ""},
                    )
                ],
            )

        if "read file" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_file_read",
                        name="read_workspace_file",
                        arguments={"path": "notes.txt"},
                    )
                ],
            )

        if "delete file" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_file_del",
                        name="delete_workspace_file",
                        arguments={"path": "notes.txt"},
                    )
                ],
            )
        if "start pomodoro" in user_text or "focus" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_pomo_1",
                        name="start_pomodoro",
                        arguments={},
                    )
                ],
            )

        # Default text response
        return AIResponse(
            content=f"Hello! I am your AI assistant. I received: '{last_msg.get('content', '')}'."
        )



class OpenAICompatibleProvider(AIProvider):
    """Provider for OpenAI, Groq, Ollama, or vLLM endpoints via HTTP JSON API."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.api_key = self.settings.ai_api_key or "mock-key"
        self.model = self.settings.ai_model
        self.base_url = self.settings.ai_base_url.rstrip("/")

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AIResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=30) as response:
                resp_bytes = response.read()
                data = json.loads(resp_bytes.decode("utf-8"))

            choice = data["choices"][0]["message"]
            content = choice.get("content")
            raw_tool_calls = choice.get("tool_calls", [])

            parsed_tool_calls = []
            for tc in raw_tool_calls:
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except Exception:
                    args = {}
                parsed_tool_calls.append(
                    ToolCall(
                        id=tc.get("id", "call_unknown"),
                        name=func.get("name", ""),
                        arguments=args,
                    )
                )

            return AIResponse(content=content, tool_calls=parsed_tool_calls)
        except Exception as err:
            return AIResponse(
                content=f"Error connecting to AI Provider ({self.model}): {str(err)}"
            )


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    """Factory method to get the configured AIProvider."""
    s = settings or get_settings()
    if s.ai_provider == "openai":
        return OpenAICompatibleProvider(s)
    return MockAIProvider()
