"""AI Provider abstraction layer.

Defines a vendor-agnostic interface for text generation and tool calling.
Provides a MockAIProvider for offline testing and an OpenAICompatibleProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json

import logging
import time
from typing import Any, Iterator
import urllib.error
import urllib.request

from app.core.config import PROJECT_ROOT, Settings, get_settings

logger = logging.getLogger(__name__)


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

        err_obj = err_data.get("error") if isinstance(err_data, dict) else {}
        err_dict = err_obj if isinstance(err_obj, dict) else {}
        err_code = err_dict.get("code", "")
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
                err_msg = err_dict.get("message", "") if isinstance(err_obj, dict) else (str(err_obj) if err_obj else "")
                if err_msg:
                    msg = f"⚠️ Rate limit: {err_msg}"
                else:
                    msg = "The AI service is rate-limited right now — please wait a moment and try again."
            return AIResponse(content=msg)
        return AIResponse(
            content=f"Error connecting to AI Provider ({self.model}): HTTP Error {http_err.code}: {http_err.reason}"
        )


# Global runtime state
_runtime_ai_mode: str | None = None
_runtime_active_provider: str | None = None
_runtime_provider_configs: dict[str, dict[str, Any]] = {}

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "ChatGPT (OpenAI)",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "base_url": "https://api.openai.com/v1",
        "key_hint": "Enter your OpenAI API key (sk-...)",
        "is_local": False,
    },
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-1.5-flash",
        "models": ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_hint": "Enter your Google AI Studio API key (AIza...)",
        "is_local": False,
    },
    "groq": {
        "label": "Groq Cloud",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "mixtral-8x7b-32768"],
        "base_url": "https://api.groq.com/openai/v1",
        "key_hint": "Enter your Groq API key (gsk_...)",
        "is_local": False,
    },
    "grok": {
        "label": "xAI Grok",
        "default_model": "grok-beta",
        "models": ["grok-beta", "grok-2-latest"],
        "base_url": "https://api.x.ai/v1",
        "key_hint": "Enter your xAI Grok API key (xai-...)",
        "is_local": False,
    },
    "offline": {
        "label": "Offline (Local Ollama)",
        "default_model": "qwen2.5:1.5b",
        "models": ["qwen2.5:1.5b", "llama3.2", "mistral", "deepseek-r1:1.5b"],
        "base_url": "http://localhost:11434/v1",
        "key_hint": "No API key required for local Ollama",
        "is_local": True,
    },
    "mock": {
        "label": "Mock (Simulator)",
        "default_model": "mock",
        "models": ["mock"],
        "base_url": "local://mock",
        "key_hint": "Offline test simulator",
        "is_local": True,
    },
}


def normalize_provider_name(provider: str | None) -> str:
    """Normalize user or config provider strings to canonical keys."""
    if not provider:
        return "groq"
    p = provider.strip().lower()
    if p in ("gpt", "chatgpt", "openai"):
        return "openai"
    if p in ("gemini", "google"):
        return "gemini"
    if p in ("groq",):
        return "groq"
    if p in ("grok", "xai"):
        return "grok"
    if p in ("offline", "ollama", "local"):
        return "offline"
    if p in ("mock", "test"):
        return "mock"
    return p


def update_env_settings(updates: dict[str, str]) -> None:
    """Safely update or add key-value pairs in the project .env file."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        content = env_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        keys_seen: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or not stripped or "=" not in stripped:
                new_lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f'{key}="{updates[key]}"')
                keys_seen.add(key)
            else:
                new_lines.append(line)
        for k, v in updates.items():
            if k not in keys_seen:
                new_lines.append(f'{k}="{v}"')
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        get_settings.cache_clear()
    except Exception as exc:
        logger.warning("Could not update .env file: %s", exc)


def get_active_provider_name() -> str:
    """Determine the currently active provider name."""
    global _runtime_active_provider, _runtime_ai_mode
    if _runtime_active_provider is not None:
        if _runtime_ai_mode == "offline":
            return "offline"
        return _runtime_active_provider

    s = get_settings()
    if _runtime_ai_mode == "offline":
        return "offline"
    elif _runtime_ai_mode == "mock":
        return "mock"

    if s.ai_mode == "offline" or s.ai_provider == "ollama":
        return "offline"
    if s.ai_provider == "mock":
        return "mock"

    return normalize_provider_name(s.online_ai_provider or s.ai_provider or "groq")


def parse_user_custom_keys(user: Any) -> dict[str, str]:
    """Extract custom API keys dictionary from a User object if set."""
    if not user:
        return {}
    keys_raw = getattr(user, "custom_api_keys", None)
    if not keys_raw:
        return {}
    if isinstance(keys_raw, dict):
        return {str(k).lower(): str(v).strip() for k, v in keys_raw.items() if v}
    if isinstance(keys_raw, str) and keys_raw.strip():
        try:
            data = json.loads(keys_raw)
            if isinstance(data, dict):
                return {str(k).lower(): str(v).strip() for k, v in data.items() if v}
        except Exception:
            return {}
    return {}


def get_provider_config(
    provider_name: str,
    settings: Settings | None = None,
    user: Any = None,
    custom_keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve complete configuration (model, api_key, base_url, is_local) for a provider.
    
    If user or custom_keys is provided, any per-user custom API key takes precedence
    over system default keys in .env. If not specified by the user, default system keys apply.
    """
    canonical = normalize_provider_name(provider_name)
    preset = PROVIDER_PRESETS.get(canonical, PROVIDER_PRESETS["groq"])
    s = settings or get_settings()

    runtime_cfg = _runtime_provider_configs.get(canonical, {})

    # Defaults from preset
    default_model = preset["default_model"]
    default_url = preset["base_url"]
    is_local = preset.get("is_local", False)

    # Check for user-specific custom key
    if custom_keys is None and user is not None:
        custom_keys = parse_user_custom_keys(user)
    user_key = custom_keys.get(canonical) if custom_keys else None
    is_custom = bool(user_key)

    # Resolve from Settings based on provider
    active_s_provider = normalize_provider_name(s.ai_provider)
    explicit_key = s.ai_api_key if active_s_provider == canonical and s.ai_api_key else None
    explicit_model = s.ai_model if active_s_provider == canonical and s.ai_model else None
    explicit_url = s.ai_base_url if active_s_provider == canonical and s.ai_base_url else None

    if canonical == "openai":
        cfg_key = (
            user_key
            or explicit_key
            or runtime_cfg.get("api_key")
            or s.openai_api_key
            or (s.online_ai_api_key if normalize_provider_name(s.online_ai_provider) in ("openai", "gpt") else None)
            or (s.ai_api_key if active_s_provider in ("openai", "gpt") else None)
        )
        cfg_model = explicit_model or runtime_cfg.get("model") or s.openai_model or default_model
        cfg_url = explicit_url or runtime_cfg.get("base_url") or s.openai_base_url or default_url
    elif canonical == "gemini":
        cfg_key = (
            user_key
            or explicit_key
            or runtime_cfg.get("api_key")
            or s.gemini_api_key
            or (s.online_ai_api_key if normalize_provider_name(s.online_ai_provider) == "gemini" else None)
            or (s.ai_api_key if active_s_provider == "gemini" else None)
        )
        cfg_model = explicit_model or runtime_cfg.get("model") or s.gemini_model or default_model
        cfg_url = explicit_url or runtime_cfg.get("base_url") or s.gemini_base_url or default_url
    elif canonical == "grok":
        cfg_key = (
            user_key
            or explicit_key
            or runtime_cfg.get("api_key")
            or s.grok_api_key
            or (s.online_ai_api_key if normalize_provider_name(s.online_ai_provider) in ("grok", "xai") else None)
            or (s.ai_api_key if active_s_provider in ("grok", "xai") else None)
        )
        cfg_model = explicit_model or runtime_cfg.get("model") or s.grok_model or default_model
        cfg_url = explicit_url or runtime_cfg.get("base_url") or s.grok_base_url or default_url
    elif canonical == "offline":
        cfg_key = explicit_key or runtime_cfg.get("api_key") or s.offline_ai_api_key or "ollama"
        cfg_model = explicit_model or runtime_cfg.get("model") or s.offline_ai_model or default_model
        cfg_url = explicit_url or runtime_cfg.get("base_url") or s.offline_ai_base_url or default_url
        is_local = True
    elif canonical == "mock":
        cfg_key = "mock-key"
        cfg_model = "mock"
        cfg_url = "local://mock"
        is_local = True
    else:  # groq or generic
        cfg_key = (
            user_key
            or explicit_key
            or runtime_cfg.get("api_key")
            or s.groq_api_key
            or (s.online_ai_api_key if normalize_provider_name(s.online_ai_provider) == "groq" else None)
            or (s.ai_api_key if active_s_provider == "groq" else None)
        )
        # Prevent OpenAI keys accidentally mapped to Groq
        if cfg_key and cfg_key.startswith("sk-proj-"):
            cfg_key = None
        cfg_model = explicit_model or runtime_cfg.get("model") or s.groq_model or default_model
        cfg_url = explicit_url or runtime_cfg.get("base_url") or s.groq_base_url or default_url

    if canonical in ("gemini", "groq", "grok") and cfg_key in ("mock-key", ""):
        cfg_key = None

    return {
        "provider": canonical,
        "model": cfg_model,
        "api_key": cfg_key,
        "base_url": cfg_url,
        "is_local": is_local,
        "is_custom": is_custom,
    }



def get_current_ai_mode() -> str:
    """Return the active AI mode ('online', 'offline', or 'mock')."""
    global _runtime_ai_mode
    if _runtime_ai_mode is not None:
        return _runtime_ai_mode
    active = get_active_provider_name()
    if active == "mock":
        return "mock"
    if active in ("offline", "ollama"):
        return "offline"
    return "online"


def set_current_ai_mode(mode: str) -> dict[str, Any]:
    """Switch active AI mode at runtime ('online' or 'offline')."""
    global _runtime_ai_mode, _runtime_active_provider
    mode_clean = mode.strip().lower()
    if mode_clean in ("offline", "local", "ollama"):
        _runtime_ai_mode = "offline"
        _runtime_active_provider = "offline"
    elif mode_clean in ("mock", "test"):
        _runtime_ai_mode = "mock"
        _runtime_active_provider = "mock"
    else:
        _runtime_ai_mode = "online"
        # If active was offline or mock, restore an online provider
        if _runtime_active_provider in ("offline", "mock", None):
            s = get_settings()
            _runtime_active_provider = normalize_provider_name(s.online_ai_provider or s.ai_provider or "openai")
    return get_ai_status()


def set_ai_configuration(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Update AI provider and model configuration at runtime, with optional .env persistence."""
    global _runtime_active_provider, _runtime_ai_mode, _runtime_provider_configs

    canonical = normalize_provider_name(provider)
    preset = PROVIDER_PRESETS.get(canonical, PROVIDER_PRESETS["groq"])

    current_cfg = get_provider_config(canonical)
    final_model = (model.strip() if model and model.strip() else None) or current_cfg["model"] or preset["default_model"]
    final_base_url = (base_url.strip() if base_url and base_url.strip() else None) or current_cfg["base_url"] or preset["base_url"]
    final_key = (api_key.strip() if api_key and api_key.strip() else None) or current_cfg["api_key"]

    _runtime_provider_configs[canonical] = {
        "model": final_model,
        "base_url": final_base_url,
        "api_key": final_key,
    }

    _runtime_active_provider = canonical
    if canonical in ("offline", "ollama"):
        _runtime_ai_mode = "offline"
    elif canonical == "mock":
        _runtime_ai_mode = "mock"
    else:
        _runtime_ai_mode = "online"

    if persist:
        env_updates: dict[str, str] = {
            "AI_MODE": "offline" if canonical in ("offline", "ollama") else "online",
            "AI_PROVIDER": canonical if canonical != "offline" else "ollama",
        }
        if canonical == "openai":
            if final_key:
                env_updates["OPENAI_API_KEY"] = final_key
                env_updates["ONLINE_AI_API_KEY"] = final_key
                env_updates["AI_API_KEY"] = final_key
            env_updates["OPENAI_MODEL"] = final_model
            env_updates["ONLINE_AI_MODEL"] = final_model
            env_updates["AI_MODEL"] = final_model
            env_updates["OPENAI_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_BASE_URL"] = final_base_url
            env_updates["AI_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_PROVIDER"] = "openai"
        elif canonical == "gemini":
            if final_key:
                env_updates["GEMINI_API_KEY"] = final_key
                env_updates["ONLINE_AI_API_KEY"] = final_key
                env_updates["AI_API_KEY"] = final_key
            env_updates["GEMINI_MODEL"] = final_model
            env_updates["ONLINE_AI_MODEL"] = final_model
            env_updates["AI_MODEL"] = final_model
            env_updates["GEMINI_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_BASE_URL"] = final_base_url
            env_updates["AI_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_PROVIDER"] = "gemini"
        elif canonical == "groq":
            if final_key:
                env_updates["GROQ_API_KEY"] = final_key
                env_updates["ONLINE_AI_API_KEY"] = final_key
                env_updates["AI_API_KEY"] = final_key
            env_updates["GROQ_MODEL"] = final_model
            env_updates["ONLINE_AI_MODEL"] = final_model
            env_updates["AI_MODEL"] = final_model
            env_updates["GROQ_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_BASE_URL"] = final_base_url
            env_updates["AI_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_PROVIDER"] = "groq"
        elif canonical == "grok":
            if final_key:
                env_updates["GROK_API_KEY"] = final_key
                env_updates["ONLINE_AI_API_KEY"] = final_key
                env_updates["AI_API_KEY"] = final_key
            env_updates["GROK_MODEL"] = final_model
            env_updates["ONLINE_AI_MODEL"] = final_model
            env_updates["AI_MODEL"] = final_model
            env_updates["GROK_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_BASE_URL"] = final_base_url
            env_updates["AI_BASE_URL"] = final_base_url
            env_updates["ONLINE_AI_PROVIDER"] = "grok"
        elif canonical == "offline":
            env_updates["OFFLINE_AI_PROVIDER"] = "ollama"
            env_updates["OFFLINE_AI_MODEL"] = final_model
            env_updates["OFFLINE_AI_BASE_URL"] = final_base_url
            env_updates["AI_PROVIDER"] = "ollama"
            env_updates["AI_MODEL"] = final_model
            env_updates["AI_BASE_URL"] = final_base_url

        update_env_settings(env_updates)

    return get_ai_status()


def test_ai_provider_connection(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    user: Any = None,
) -> dict[str, Any]:
    """Test AI model connection with a quick completion check."""
    canonical = normalize_provider_name(provider)
    preset = PROVIDER_PRESETS.get(canonical, PROVIDER_PRESETS["groq"])

    current_cfg = get_provider_config(canonical, user=user)
    final_model = (model.strip() if model and model.strip() else None) or current_cfg["model"] or preset["default_model"]
    final_base_url = (base_url.strip() if base_url and base_url.strip() else None) or current_cfg["base_url"] or preset["base_url"]
    
    if api_key is not None:
        final_key = api_key.strip() or None
    else:
        final_key = current_cfg.get("api_key")

    is_local = preset.get("is_local", False)

    if canonical == "mock":
        return {
            "ok": True,
            "provider": canonical,
            "model": final_model,
            "latency_ms": 10,
            "status": "connected",
            "message": "Mock AI Provider responded immediately.",
        }

    # For cloud providers, check if an API key is present
    if not is_local and (not final_key or final_key == "mock-key"):
        label = preset.get("label", canonical.title())
        hint = preset.get("key_hint", "Enter your API key")
        return {
            "ok": False,
            "provider": canonical,
            "model": final_model,
            "latency_ms": 0,
            "status": "missing_key",
            "message": f"API key not configured yet for {label}. ({hint})",
        }

    provider_instance = OpenAICompatibleProvider(
        base_url=final_base_url,
        api_key=final_key or ("ollama" if is_local else "mock-key"),
        model=final_model,
        is_local=is_local,
    )

    t0 = time.time()
    try:
        resp = provider_instance.generate([{"role": "user", "content": "Hello, respond with 'OK'."}])
        latency_ms = round((time.time() - t0) * 1000)
        if resp.content and ("Error connecting to AI Provider" in resp.content or "HTTP Error" in resp.content):
            msg = resp.content
            if "Connection refused" in msg or "11434" in msg:
                msg = f"Cannot reach local Ollama at {final_base_url}. Make sure Ollama is running ('ollama serve')."
            return {
                "ok": False,
                "provider": canonical,
                "model": final_model,
                "latency_ms": latency_ms,
                "status": "error",
                "message": msg,
            }
        return {
            "ok": True,
            "provider": canonical,
            "model": final_model,
            "latency_ms": latency_ms,
            "status": "connected",
            "message": f"Connection verified in {latency_ms}ms! (Model: {final_model})",
        }
    except Exception as exc:
        latency_ms = round((time.time() - t0) * 1000)
        err_msg = str(exc)
        if "Connection refused" in err_msg or "11434" in err_msg:
            err_msg = f"Cannot reach local Ollama at {final_base_url}. Make sure Ollama is running ('ollama serve')."
        return {
            "ok": False,
            "provider": canonical,
            "model": final_model,
            "latency_ms": latency_ms,
            "status": "error",
            "message": f"Connection failed: {err_msg}",
        }


def test_all_ai_providers(user: Any = None) -> dict[str, Any]:
    """Test connectivity for all supported AI providers and return aggregated status."""
    providers_order = ["openai", "offline", "gemini", "groq", "grok", "mock"]
    results: dict[str, dict[str, Any]] = {}
    connected_count = 0
    missing_key_count = 0
    error_count = 0

    for p in providers_order:
        res = test_ai_provider_connection(p, user=user)
        results[p] = res
        if res.get("status") == "connected" or res.get("ok"):
            connected_count += 1
        elif res.get("status") == "missing_key":
            missing_key_count += 1
        else:
            error_count += 1

    return {
        "summary": {
            "total": len(providers_order),
            "connected": connected_count,
            "missing_key": missing_key_count,
            "error": error_count,
        },
        "providers": results,
    }


def get_ai_status(user: Any = None) -> dict[str, Any]:
    """Get metadata about current and available AI configurations."""
    s = get_settings()
    active = get_active_provider_name()
    is_online = active not in ("offline", "ollama", "mock")
    mode = "mock" if active == "mock" else ("online" if is_online else "offline")

    user_keys = parse_user_custom_keys(user)
    active_cfg = get_provider_config(active, s, user=user)
    active_model = active_cfg.get("model")
    active_url = active_cfg.get("base_url")

    # Map for tests expecting 'ollama' as the active_provider when offline
    reported_active_provider = "ollama" if active in ("offline", "ollama") else active

    providers_info: dict[str, dict[str, Any]] = {}
    for p_key, preset in PROVIDER_PRESETS.items():
        if p_key == "mock":
            continue
        if p_key == "offline":
            off_cfg = get_provider_config("offline", s, user=user)
            providers_info[p_key] = {
                "key": p_key,
                "label": preset["label"],
                "default_model": preset["default_model"],
                "models": preset["models"],
                "base_url": off_cfg.get("base_url") or preset["base_url"],
                "configured_model": off_cfg.get("model") or preset["default_model"],
                "has_key": True,
                "key_preview": "Local (No key needed)",
                "is_local": True,
                "key_hint": preset.get("key_hint", ""),
                "has_custom_key": False,
                "is_using_custom_key": False,
                "custom_key_preview": "",
            }
            continue

        cfg = get_provider_config(p_key, s, user=user)
        key_val = cfg.get("api_key") or ""
        masked_key = ""
        if key_val and key_val not in ("ollama", "mock-key"):
            if len(key_val) > 8:
                masked_key = f"{key_val[:4]}...{key_val[-4:]}"
            else:
                masked_key = "****"

        custom_k = user_keys.get(p_key)
        has_custom = bool(custom_k)
        custom_preview = f"{custom_k[:4]}...{custom_k[-4:]}" if (custom_k and len(custom_k) > 8) else ("****" if custom_k else "")

        providers_info[p_key] = {
            "key": p_key,
            "label": preset["label"],
            "default_model": preset["default_model"],
            "models": preset["models"],
            "base_url": cfg.get("base_url") or preset["base_url"],
            "configured_model": cfg.get("model") or preset["default_model"],
            "has_key": bool(key_val and key_val not in ("mock-key", "")),
            "key_preview": masked_key,
            "is_local": preset.get("is_local", False),
            "key_hint": preset.get("key_hint", ""),
            "has_custom_key": has_custom,
            "is_using_custom_key": has_custom,
            "custom_key_preview": custom_preview,
        }

    return {
        "mode": mode,
        "is_online": is_online,
        "active_provider": reported_active_provider,
        "active_model": active_model,
        "active_base_url": active_url,
        "online_provider": active if is_online else (s.online_ai_provider or "openai"),
        "online_model": active_model if is_online else (s.online_ai_model or "gpt-4o-mini"),
        "offline_provider": "ollama",
        "offline_model": s.offline_ai_model or "qwen2.5:1.5b",
        "providers": providers_info,
    }


def get_ai_provider(
    settings: Settings | None = None,
    mode: str | None = None,
    user: Any = None,
) -> AIProvider:
    """Factory method to get the configured AIProvider based on active or requested mode."""
    s = settings or get_settings()

    if s.ai_provider == "mock" or (settings and settings.ai_provider == "mock") or mode == "mock" or _runtime_ai_mode == "mock":
        return MockAIProvider()

    if settings and settings.ai_provider:
        active = normalize_provider_name(settings.ai_provider)
    else:
        active = get_active_provider_name()

    if mode is not None:
        mode_clean = mode.strip().lower()
        if mode_clean in ("mock", "test"):
            return MockAIProvider()
        elif mode_clean in ("offline", "local", "ollama"):
            active = "offline"
        else:
            if active in ("offline", "mock"):
                active = normalize_provider_name(s.online_ai_provider or s.ai_provider or "openai")

    if active == "mock":
        return MockAIProvider()

    # Admin-only check: offline model is restricted to administrators
    if active == "offline" and user is not None and getattr(user, "role", "user") != "admin":
        active = normalize_provider_name(s.online_ai_provider or "openai")

    cfg = get_provider_config(active, s, user=user)
    is_local = active in ("offline", "ollama") or cfg.get("is_local", False)
    api_key = cfg.get("api_key")

    # Graceful fallback: If an online cloud provider is chosen but has no valid API key configured:
    if not is_local and (not api_key or api_key == "mock-key"):
        # Check if openai has a configured key
        openai_cfg = get_provider_config("openai", s, user=user)
        if openai_cfg.get("api_key") and openai_cfg.get("api_key") != "mock-key":
            logger.warning("Provider '%s' has no API key; falling back to configured OpenAI provider", active)
            cfg = openai_cfg
            active = "openai"
            api_key = cfg.get("api_key")
        elif s.offline_ai_base_url:
            logger.warning("Provider '%s' has no API key; falling back to offline provider", active)
            cfg = get_provider_config("offline", s, user=user)
            active = "offline"
            is_local = True
            api_key = cfg.get("api_key")

    return OpenAICompatibleProvider(
        settings=s,
        base_url=cfg["base_url"],
        api_key=api_key or ("ollama" if is_local else "mock-key"),
        model=cfg["model"],
        is_local=is_local,
    )

