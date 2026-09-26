"""AI Provider abstraction layer.

Defines a vendor-agnostic interface for text generation and tool calling.
Provides a MockAIProvider for offline testing and an OpenAICompatibleProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json

from typing import Any, Iterator
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

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream text tokens as they arrive, yielding a final response dictionary at the end.

        Yields items of format:
          - {"type": "delta", "content": "..."}
          - {"type": "response", "response": AIResponse(...)}
        """
        resp = self.generate(messages, tools=tools)
        if resp.content:
            yield {"type": "delta", "content": resp.content}
        yield {"type": "response", "response": resp}


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

        if "delete task" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_task_del",
                        name="delete_task",
                        arguments={"task_id": 1},
                    )
                ],
            )

        if "delete project" in user_text:
            return AIResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_mock_proj_del",
                        name="delete_project",
                        arguments={"project_id": 1},
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

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        resp = self.generate(messages, tools=tools)
        if resp.content:
            # Yield in small token-sized chunks to simulate progressive arrival
            words = resp.content.split(" ")
            for i, w in enumerate(words):
                suffix = " " if i < len(words) - 1 else ""
                yield {"type": "delta", "content": w + suffix}
        yield {"type": "response", "response": resp}


class OpenAICompatibleProvider(AIProvider):
    """Provider for OpenAI, Groq, Ollama, or vLLM endpoints via HTTP JSON API."""

    def __init__(
        self,
        settings: Settings | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        is_local: bool | None = None,
    ):
        s = settings or get_settings()
        self.base_url = (base_url or s.ai_base_url).rstrip("/")
        self.api_key = api_key or s.ai_api_key or "mock-key"
        self.model = model or s.ai_model
        if is_local is not None:
            self.is_local = is_local
        else:
            self.is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url or "ollama" in (s.ai_provider or "").lower()

    def _build_request_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> tuple[str, dict[str, str], bytes]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PersonalProductivityAssistant/1.0",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if self.is_local:
            payload["keep_alive"] = -1
            payload["options"] = {
                "num_thread": 4,
                "num_ctx": 2048,
            }
        else:
            payload["max_tokens"] = 800

        req_data = json.dumps(payload).encode("utf-8")
        return url, headers, req_data

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AIResponse:
        url, headers, req_data = self._build_request_payload(messages, tools=tools, stream=False)
        try:
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as response:
                resp_bytes = response.read()
                data = json.loads(resp_bytes.decode("utf-8"))

            choice = data["choices"][0]["message"]
            content = choice.get("content")

            if content and "<think>" in content:
                import re as _re
                content = _re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                if not content:
                    content = None

            raw_tool_calls = choice.get("tool_calls", [])
            parsed_tool_calls = self._parse_tool_calls_list(raw_tool_calls)
            return AIResponse(content=content, tool_calls=parsed_tool_calls)
        except urllib.error.HTTPError as http_err:
            return self._handle_http_error(http_err)
        except Exception as err:
            return AIResponse(
                content=f"Error connecting to AI Provider ({self.model}): {str(err)}"
            )

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        url, headers, req_data = self._build_request_payload(messages, tools=tools, stream=True)
        try:
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as response:
                assembled_content: list[str] = []
                tool_calls_map: dict[int, dict[str, Any]] = {}
                inside_think_block = False
                think_buffer: list[str] = []

                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except Exception:
                            continue

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}

                        # Handle content delta
                        content_piece = delta.get("content")
                        if content_piece:
                            assembled_content.append(content_piece)

                            # Filter reasoning tags (<think>...</think>)
                            if "<think>" in content_piece or inside_think_block:
                                inside_think_block = True
                                think_buffer.append(content_piece)
                                full_think = "".join(think_buffer)
                                if "</think>" in full_think:
                                    inside_think_block = False
                                    after_think = full_think.split("</think>", 1)[1]
                                    think_buffer.clear()
                                    if after_think:
                                        yield {"type": "delta", "content": after_think}
                            else:
                                yield {"type": "delta", "content": content_piece}

                        # Handle tool call delta fragments
                        delta_tool_calls = delta.get("tool_calls") or []
                        for tc_delta in delta_tool_calls:
                            idx = tc_delta.get("index", 0)
                            if idx not in tool_calls_map:
                                tool_calls_map[idx] = {
                                    "id": tc_delta.get("id") or f"call_{idx}",
                                    "name": "",
                                    "arguments": "",
                                }
                            entry = tool_calls_map[idx]
                            if tc_delta.get("id"):
                                entry["id"] = tc_delta["id"]
                            func = tc_delta.get("function") or {}
                            if func.get("name"):
                                entry["name"] += func["name"]
                            if func.get("arguments"):
                                entry["arguments"] += func["arguments"]

                # Assemble final response
                full_text = "".join(assembled_content).strip()
                if full_text and "<think>" in full_text:
                    import re as _re
                    full_text = _re.sub(r"<think>[\s\S]*?</think>", "", full_text).strip()
                final_content = full_text if full_text else None

                parsed_tool_calls: list[ToolCall] = []
                for idx in sorted(tool_calls_map.keys()):
                    tc_dict = tool_calls_map[idx]
                    args_str = tc_dict.get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) and args_str.strip() else {}
                    except Exception:
                        args = {}
                    parsed_tool_calls.append(
                        ToolCall(
                            id=tc_dict.get("id", f"call_{idx}"),
                            name=tc_dict.get("name", ""),
                            arguments=args,
                        )
                    )

                final_resp = AIResponse(content=final_content, tool_calls=parsed_tool_calls)
                yield {"type": "response", "response": final_resp}
        except urllib.error.HTTPError as http_err:
            err_resp = self._handle_http_error(http_err)
            if err_resp.content:
                yield {"type": "delta", "content": err_resp.content}
            yield {"type": "response", "response": err_resp}
        except Exception as err:
            err_msg = f"Error connecting to AI Provider ({self.model}): {str(err)}"
            yield {"type": "delta", "content": err_msg}
            yield {"type": "response", "response": AIResponse(content=err_msg)}

    def _parse_tool_calls_list(self, raw_tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
        parsed = []
        for tc in raw_tool_calls:
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception:
                args = {}
            parsed.append(
                ToolCall(
                    id=tc.get("id", "call_unknown"),
                    name=func.get("name", ""),
                    arguments=args,
                )
            )
        return parsed

    def _handle_http_error(self, http_err: urllib.error.HTTPError) -> AIResponse:
        try:
            err_body = http_err.read().decode("utf-8")
            err_data = json.loads(err_body)
        except Exception:
            err_body = ""
            err_data = {}

        err_code = (err_data.get("error") or {}).get("code", "")
        is_rate_limit = http_err.code == 429 or (
            http_err.code == 400 and err_code == "rate_limit_exceeded"
        )

        if is_rate_limit:
            retry_after = http_err.headers.get("retry-after")
            if retry_after:
                try:
                    secs = int(float(retry_after))
                    msg = f"The AI service is rate-limited right now — please try again in ~{secs} seconds."
                except Exception:
                    msg = f"The AI service is rate-limited right now (retry-after: {retry_after}) — please wait a moment and try again."
            else:
                err_msg = (err_data.get("error") or {}).get("message", "")
                if err_msg:
                    msg = f"⚠️ Rate limit: {err_msg}"
                else:
                    msg = "The AI service is rate-limited right now — please wait a moment and try again."
            return AIResponse(content=msg)
        return AIResponse(
            content=f"Error connecting to AI Provider ({self.model}): HTTP Error {http_err.code}: {http_err.reason}"
        )


# Global runtime mode toggle state
_runtime_ai_mode: str | None = None


def get_current_ai_mode() -> str:
    """Return the active AI mode ('online', 'offline', or 'mock')."""
    global _runtime_ai_mode
    if _runtime_ai_mode is not None:
        return _runtime_ai_mode
    s = get_settings()
    return s.ai_mode or ("offline" if s.ai_provider == "ollama" else "online")


def set_current_ai_mode(mode: str) -> dict[str, Any]:
    """Switch active AI mode at runtime."""
    global _runtime_ai_mode
    mode_clean = mode.strip().lower()
    if mode_clean in ("offline", "local"):
        _runtime_ai_mode = "offline"
    elif mode_clean in ("mock", "test"):
        _runtime_ai_mode = "mock"
    else:
        _runtime_ai_mode = "online"
    return get_ai_status()


def get_ai_status() -> dict[str, Any]:
    """Get metadata about current and available AI configurations."""
    s = get_settings()
    mode = get_current_ai_mode()

    if mode == "offline":
        active_provider = s.offline_ai_provider or "ollama"
        active_model = s.offline_ai_model or "qwen2.5:1.5b"
        active_url = s.offline_ai_base_url or "http://localhost:11434/v1"
    elif mode == "mock":
        active_provider = "mock"
        active_model = "mock"
        active_url = "local://mock"
    else:
        active_provider = s.online_ai_provider or s.ai_provider or "groq"
        active_model = s.online_ai_model or s.ai_model or "qwen/qwen3.8-27b"
        active_url = s.online_ai_base_url or s.ai_base_url or "https://api.groq.com/openai/v1"

    return {
        "mode": mode,
        "is_online": mode == "online",
        "active_provider": active_provider,
        "active_model": active_model,
        "active_base_url": active_url,
        "online_provider": s.online_ai_provider or "groq",
        "online_model": s.online_ai_model or "qwen/qwen3.8-27b",
        "offline_provider": s.offline_ai_provider or "ollama",
        "offline_model": s.offline_ai_model or "qwen2.5:1.5b",
    }


def get_ai_provider(settings: Settings | None = None, mode: str | None = None) -> AIProvider:
    """Factory method to get the configured AIProvider based on active or requested mode."""
    s = settings or get_settings()
    effective_mode = mode or get_current_ai_mode()

    if effective_mode == "mock" or s.ai_provider == "mock":
        return MockAIProvider()

    if effective_mode == "offline" or s.ai_provider == "ollama":
        return OpenAICompatibleProvider(
            base_url=s.offline_ai_base_url or s.ai_base_url or "http://localhost:11434/v1",
            api_key=s.offline_ai_api_key or s.ai_api_key or "ollama",
            model=s.offline_ai_model or s.ai_model or "qwen2.5:1.5b",
            is_local=True,
        )

    # Online mode (Cloud API like Groq or OpenAI)
    online_url = s.online_ai_base_url or s.ai_base_url or "https://api.groq.com/openai/v1"
    online_key = s.ai_api_key or s.online_ai_api_key or "mock-key"
    online_model = s.online_ai_model or s.ai_model or "qwen/qwen3.8-27b"
    return OpenAICompatibleProvider(
        base_url=online_url,
        api_key=online_key,
        model=online_model,
        is_local=False,
    )
