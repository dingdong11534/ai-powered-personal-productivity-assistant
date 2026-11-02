"""Assistant Core Engine orchestrating message flow, context, tool execution, and response synthesis."""

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.ai.context import ContextBuilder
from app.ai.planner import DailyPlanner
from app.ai.provider import AIProvider, AIResponse, get_ai_provider
from app.ai.tools.implementations import get_default_tool_registry
from app.ai.tools.registry import ToolRegistry
from app.conversations.schemas import MessageCreate, MessageRead
from app.conversations.service import ConversationService


class AssistantCore:
    """Orchestrates structured tool calls, context retrieval, and response synthesis."""

    def __init__(
        self,
        session: Session,
        provider: AIProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        destructive_authorized: bool = False,
        user: Any = None,
    ):
        self.session = session
        self.user = user
        self.provider = provider or get_ai_provider(user=user)
        self.tool_registry = tool_registry or get_default_tool_registry()
        self.conv_svc = ConversationService(session)
        self.context_builder = ContextBuilder()
        self.planner = DailyPlanner()
        self.destructive_authorized = destructive_authorized


    # Hard limit: reject extremely large single messages immediately to avoid
    # unnecessary LLM calls, timeout errors, and token over-runs.
    # 12 000 characters ≈ ~3 000 tokens — safely under every provider's context window
    # while still allowing normal paragraph-length requests.
    MAX_USER_MESSAGE_CHARS = 12_000

    def _extract_task_creation_intent(self, text: str) -> dict[str, Any] | None:
        """Extract explicit task creation parameters from user message."""
        t = text.strip()
        p = 2
        p_match = re.search(
            r"(?:priority\s*(?:is|to|level)?\s*(the highest|critical|highest|high|medium|low|\d+)|(the highest|critical|highest|high|medium|low|\d+)\s+priority)",
            t,
            re.IGNORECASE,
        )
        if p_match:
            val = (p_match.group(1) or p_match.group(2)).lower()
            if any(k in val for k in ("critical", "highest", "1")):
                p = 1
            elif any(k in val for k in ("high", "2")):
                p = 2
            elif any(k in val for k in ("medium", "3")):
                p = 3
            elif any(k in val for k in ("low", "4")):
                p = 4

        m = re.search(
            r"(?:create|add|make)\s+(?:a\s+)?(?:new\s+)?(?:task|todo)(?:\s+(?:named|name|called|titled))?\s*[:\"']?\s*([^\"'\n]+)",
            t,
            re.IGNORECASE,
        )
        if m:
            raw_title = m.group(1).strip(" \"':")
            clean_title = re.sub(
                r"\s+(?:with|and set|set)\s+(?:the\s+)?priority.*$", "", raw_title, flags=re.IGNORECASE
            ).strip()
            clean_title = re.sub(
                r"\s+(?:with\s+)?(?:critical|highest|high|medium|low|\d+)\s+priority.*$", "", clean_title, flags=re.IGNORECASE
            ).strip()
            clean_title = re.sub(r"\s+priority\s+.*$", "", clean_title, flags=re.IGNORECASE).strip()
            if clean_title:
                return {"title": clean_title, "priority": p}
        return None

    def _find_pending_task_creation(
        self, db_messages: list[MessageRead], user_text: str
    ) -> dict[str, Any] | None:
        """Find pending or implied task creation intent from the message or recent turns."""
        direct = self._extract_task_creation_intent(user_text)
        if direct:
            return direct

        lower = user_text.lower().strip()
        is_followup = any(w in lower for w in ("do that", "proceed", "go ahead", "create it", "make it", "add it", "do it"))
        if not is_followup:
            return None

        # Look backward through recent messages
        for msg in reversed(db_messages[-6:]):
            if not msg.content:
                continue
            asst_m = re.search(
                r'(?:create(?: your)? new task\s+titled|task titled|new task titled)\s+["\']?([^"\'\n.,]+)["\']?',
                msg.content,
                re.IGNORECASE,
            )
            if asst_m:
                title = asst_m.group(1).strip()
                p = 1 if "critical" in lower or any("critical" in (m.content or "").lower() for m in db_messages[-4:]) else 2
                return {"title": title, "priority": p}
            user_intent = self._extract_task_creation_intent(msg.content)
            if user_intent:
                return user_intent
        return None

    def _find_pending_destructive_tool_call(
        self, db_messages: list[MessageRead]
    ) -> tuple[str, dict[str, Any]] | None:
        """Find a recently requested destructive tool call that was blocked by permission denial."""
        for idx in range(len(db_messages) - 1, -1, -1):
            m = db_messages[idx]
            if m.role == "tool" and m.content:
                try:
                    data = json.loads(m.content)
                    if data.get("success") is False and "Permission denied" in str(data.get("error")):
                        tool_name = m.name
                        # Search backward for the assistant message that requested this tool call
                        for prev in reversed(db_messages[:idx]):
                            if prev.role == "assistant" and prev.tool_calls:
                                tc_list = json.loads(prev.tool_calls)
                                for tc in tc_list:
                                    if tc.get("id") == m.tool_call_id or tc.get("name") == tool_name:
                                        return tool_name, tc.get("arguments", {})
                except Exception:
                    pass
        return None

    def handle_user_message(self, conversation_id: int, user_content: str) -> MessageRead:
        # 0. Request size guard — stop early before any LLM call
        if len(user_content) > self.MAX_USER_MESSAGE_CHARS:
            self.conv_svc.add_message(
                conversation_id,
                MessageCreate(role="user", content=user_content),
            )
            return self.conv_svc.add_message(
                conversation_id,
                MessageCreate(
                    role="assistant",
                    content=(
                        f"⚠️ Your message is too large to process "
                        f"({len(user_content):,} characters, limit is {self.MAX_USER_MESSAGE_CHARS:,}). "
                        "Please shorten it and try again."
                    ),
                ),
            )

        # 0b. Token limit guard (100k tokens per user)
        if self.user and (getattr(self.user, "token_usage", 0) or 0) >= 100_000:
            limit_msg = (
                "⚠️ **Token limit reached**: You have reached the 100,000 token limit. "
                "Further AI generation is paused for your account."
            )
            return self.conv_svc.add_message(
                conversation_id,
                MessageCreate(role="assistant", content=limit_msg),
            )

        # 1. Save user message to database
        self.conv_svc.add_message(
            conversation_id,
            MessageCreate(role="user", content=user_content),
        )


        # Check if user is explicitly authorizing a previously blocked destructive action
        if self.destructive_authorized:
            pending = self._find_pending_destructive_tool_call(self.conv_svc.get_messages(conversation_id))
            if pending:
                tool_name, tool_args = pending
                exec_result = self.tool_registry.execute_tool(
                    tool_name,
                    tool_args,
                    self.session,
                    destructive_authorized=True,
                )
                self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(
                        role="tool",
                        content=json.dumps(exec_result),
                        name=tool_name,
                    ),
                )
                if exec_result.get("success"):
                    msg = exec_result.get("data", {}).get("message") or f"Successfully executed {tool_name} as authorized."
                    resp_content = f"✅ Authorization confirmed. {msg}"
                else:
                    resp_content = f"⚠️ Authorization received, but execution failed: {exec_result.get('error')}"
                return self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(role="assistant", content=resp_content),
                )

        is_local = getattr(self.provider, "is_local", False)

        # 2. Bounded execution loop (max 5 iterations)
        max_iterations = 5
        for _ in range(max_iterations):
            # Load fresh history and format for LLM
            db_messages = self.conv_svc.get_messages(conversation_id)
            formatted_messages = self._build_prompt_messages(db_messages, user_content, is_local=is_local)

            tool_schemas = self.tool_registry.get_tools_schema(query=user_content, is_local=is_local)
            response = self.provider.generate(formatted_messages, tools=tool_schemas)

            # If no tool calls requested, check for pending task creation or return response
            if not response.tool_calls:
                pending_creation = self._find_pending_task_creation(db_messages, user_content)
                if pending_creation and _ == 0:
                    exec_result = self.tool_registry.execute_tool(
                        "create_task",
                        pending_creation,
                        self.session,
                        destructive_authorized=False,
                    )
                    self.conv_svc.add_message(
                        conversation_id,
                        MessageCreate(
                            role="tool",
                            content=json.dumps(exec_result),
                            name="create_task",
                        ),
                    )
                    if exec_result.get("success"):
                        task_data = exec_result.get("data", {})
                        p_name = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}.get(task_data.get("priority"), "High")
                        resp_content = f"✅ Created task **\"{task_data.get('title')}\"** (Priority: {p_name}, ID #{task_data.get('id')})."
                    else:
                        resp_content = f"⚠️ Could not create task: {exec_result.get('error')}"

                    return self.conv_svc.add_message(
                        conversation_id,
                        MessageCreate(role="assistant", content=resp_content),
                    )

                content = response.content or "How can I assist you with your tasks or productivity today?"
                if self.user:
                    used = max(30, (len(user_content) + len(content)) // 4)
                    self.user.token_usage = min(100_000, (self.user.token_usage or 0) + used)
                    self.session.commit()
                return self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(role="assistant", content=content),
                )


            # If tool calls were requested, record assistant message with tool calls metadata
            tool_calls_json = json.dumps([
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ])
            self.conv_svc.add_message(
                conversation_id,
                MessageCreate(
                    role="assistant",
                    content=response.content,
                    tool_calls=tool_calls_json,
                ),
            )

            # Execute each requested tool safely
            for tc in response.tool_calls:
                exec_result = self.tool_registry.execute_tool(
                    tc.name,
                    tc.arguments,
                    self.session,
                    destructive_authorized=self.destructive_authorized,
                )
                self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(
                        role="tool",
                        content=json.dumps(exec_result),
                        tool_call_id=tc.id,
                        name=tc.name,
                    ),
                )

        # Fallback if max iterations exceeded
        return self.conv_svc.add_message(
            conversation_id,
            MessageCreate(role="assistant", content="Completed tool operations."),
        )

    def handle_user_message_stream(
        self, conversation_id: int, user_content: str
    ) -> Any:
        """Stream assistant response tokens and tool status events for a user message."""
        # 0. Request size guard — stop early before any LLM call
        if len(user_content) > self.MAX_USER_MESSAGE_CHARS:
            self.conv_svc.add_message(
                conversation_id,
                MessageCreate(role="user", content=user_content),
            )
            err_msg = (
                f"⚠️ Your message is too large to process "
                f"({len(user_content):,} characters, limit is {self.MAX_USER_MESSAGE_CHARS:,}). "
                "Please shorten it and try again."
            )
            saved_msg = self.conv_svc.add_message(
                conversation_id,
                MessageCreate(role="assistant", content=err_msg),
            )
            yield {"event": "delta", "content": err_msg}
            yield {"event": "done", "message": saved_msg.model_dump(mode="json"), "message_id": saved_msg.id}
            return

        # 0b. Token limit guard (100k tokens per user)
        if self.user and (getattr(self.user, "token_usage", 0) or 0) >= 100_000:
            limit_msg = (
                "⚠️ **Token limit reached**: You have reached the 100,000 token limit. "
                "Further AI generation is paused for your account."
            )
            saved_msg = self.conv_svc.add_message(
                conversation_id,
                MessageCreate(role="assistant", content=limit_msg),
            )
            yield {"event": "delta", "content": limit_msg}
            yield {"event": "done", "message": saved_msg.model_dump(mode="json"), "message_id": saved_msg.id}
            return

        # 1. Save user message to database
        self.conv_svc.add_message(
            conversation_id,
            MessageCreate(role="user", content=user_content),
        )


        # Check if user is explicitly authorizing a previously blocked destructive action
        if self.destructive_authorized:
            pending = self._find_pending_destructive_tool_call(self.conv_svc.get_messages(conversation_id))
            if pending:
                tool_name, tool_args = pending
                yield {
                    "event": "status",
                    "stage": "tool_call",
                    "name": tool_name,
                    "arguments": tool_args,
                }
                exec_result = self.tool_registry.execute_tool(
                    tool_name,
                    tool_args,
                    self.session,
                    destructive_authorized=True,
                )
                self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(
                        role="tool",
                        content=json.dumps(exec_result),
                        name=tool_name,
                    ),
                )
                if exec_result.get("success"):
                    msg = exec_result.get("data", {}).get("message") or f"Successfully executed {tool_name} as authorized."
                    resp_content = f"✅ Authorization confirmed. {msg}"
                else:
                    resp_content = f"⚠️ Authorization received, but execution failed: {exec_result.get('error')}"

                saved_msg = self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(role="assistant", content=resp_content),
                )
                yield {"event": "delta", "content": resp_content}
                yield {"event": "done", "message": saved_msg.model_dump(mode="json"), "message_id": saved_msg.id}
                return

        is_local = getattr(self.provider, "is_local", False)

        # 2. Bounded execution loop (max 5 iterations)
        max_iterations = 5
        for _ in range(max_iterations):
            # Load fresh history and format for LLM
            db_messages = self.conv_svc.get_messages(conversation_id)
            formatted_messages = self._build_prompt_messages(db_messages, user_content, is_local=is_local)

            tool_schemas = self.tool_registry.get_tools_schema(query=user_content, is_local=is_local)
            stream_gen = self.provider.generate_stream(formatted_messages, tools=tool_schemas)

            accumulated_deltas: list[str] = []
            response = None

            for item in stream_gen:
                if item.get("type") == "delta":
                    delta_text = item.get("content", "")
                    accumulated_deltas.append(delta_text)
                    yield {"event": "delta", "content": delta_text}
                elif item.get("type") == "response":
                    response = item.get("response")

            if response is None:
                response = AIResponse(content="".join(accumulated_deltas) or None)

            # If no tool calls requested, check for pending task creation or return response
            if not response.tool_calls:
                pending_creation = self._find_pending_task_creation(db_messages, user_content)
                if pending_creation and _ == 0:
                    tc_name = "create_task"
                    tc_args = pending_creation
                    yield {
                        "event": "status",
                        "stage": "tool_call",
                        "name": tc_name,
                        "arguments": tc_args,
                    }
                    exec_result = self.tool_registry.execute_tool(
                        tc_name,
                        tc_args,
                        self.session,
                        destructive_authorized=False,
                    )
                    yield {
                        "event": "tool_result",
                        "name": tc_name,
                        "arguments": tc_args,
                        "result": exec_result,
                    }
                    self.conv_svc.add_message(
                        conversation_id,
                        MessageCreate(
                            role="tool",
                            content=json.dumps(exec_result),
                            name=tc_name,
                        ),
                    )
                    if exec_result.get("success"):
                        task_data = exec_result.get("data", {})
                        p_name = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}.get(task_data.get("priority"), "High")
                        resp_content = f"✅ Created task **\"{task_data.get('title')}\"** (Priority: {p_name}, ID #{task_data.get('id')})."
                    else:
                        resp_content = f"⚠️ Could not create task: {exec_result.get('error')}"

                    saved_msg = self.conv_svc.add_message(
                        conversation_id,
                        MessageCreate(role="assistant", content=resp_content),
                    )
                    yield {"event": "delta", "content": resp_content}
                    yield {"event": "done", "message": saved_msg.model_dump(mode="json"), "message_id": saved_msg.id}
                    return

                content = response.content or "".join(accumulated_deltas)
                if not content:
                    content = "How can I assist you with your tasks or productivity today?"
                if self.user:
                    used = max(30, (len(user_content) + len(content)) // 4)
                    self.user.token_usage = min(100_000, (self.user.token_usage or 0) + used)
                    self.session.commit()
                saved_msg = self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(role="assistant", content=content),
                )
                yield {"event": "done", "message": saved_msg.model_dump(mode="json"), "message_id": saved_msg.id}
                return


            # If tool calls were requested, record assistant message with tool calls metadata
            tool_calls_json = json.dumps([
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ])
            self.conv_svc.add_message(
                conversation_id,
                MessageCreate(
                    role="assistant",
                    content=response.content,
                    tool_calls=tool_calls_json,
                ),
            )

            # Execute each requested tool safely, emitting status event first
            for tc in response.tool_calls:
                yield {
                    "event": "status",
                    "stage": "tool_call",
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                exec_result = self.tool_registry.execute_tool(
                    tc.name,
                    tc.arguments,
                    self.session,
                    destructive_authorized=self.destructive_authorized,
                )
                yield {
                    "event": "tool_result",
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": exec_result,
                }
                self.conv_svc.add_message(
                    conversation_id,
                    MessageCreate(
                        role="tool",
                        content=json.dumps(exec_result),
                        tool_call_id=tc.id,
                        name=tc.name,
                    ),
                )

        # Fallback if max iterations exceeded
        fallback_msg = self.conv_svc.add_message(
            conversation_id,
            MessageCreate(role="assistant", content="Completed tool operations."),
        )
        yield {"event": "done", "message": fallback_msg.model_dump(mode="json"), "message_id": fallback_msg.id}

    def _build_prompt_messages(
        self, db_messages: list[MessageRead], latest_user_text: str, is_local: bool = False
    ) -> list[dict[str, Any]]:
        system_text = (
            "You are an AI Personal Productivity Assistant. "
            "You help the user manage tasks, projects, habits, schedules, reminders, pomodoro focus sessions, and notifications.\n"
            "CRITICAL OPERATIONAL RULES:\n"
            "1. When the user asks to create, add, or make a task (e.g. 'create a task name kunal with critical priority', 'add task Buy groceries', 'create todo...'):\n"
            "   - IMMEDIATELY call the tool `create_task(title=..., priority=...)`.\n"
            "   - DO NOT ask conversational questions (like 'What priority?' or 'What is the title?') if the title or intent is clear.\n"
            "   - Priority mapping: 'critical'/'highest'/urgent -> 1; 'high' -> 2; 'medium' -> 3; 'low' -> 4. Default priority is 2 (High), or 1 if critical/highest was requested.\n"
            "   - If the user says 'do that', 'proceed', 'go ahead', 'yes', or confirms a previously discussed task, immediately call `create_task` with the discussed title and priority.\n"
            "2. When the user asks about the most recent or newest task (e.g. 'delete the most recent task', 'take the task modified most recently'):\n"
            "   - Refer to the '-- Recent Tasks (Newest First) --' section in the context below. The first task listed is the most recent task.\n"
            "   - Identify its numeric ID and call the appropriate tool immediately (e.g. `delete_task(task_id=<ID>)`).\n"
            "   - NEVER claim that direct communication or fetching recent task IDs is not implemented.\n"
            "3. If the user provides a task ID or task name (e.g. '14', 'take id 14', 'delete Deepak Task'), immediately call the tool with that ID.\n"
            "4. NEVER state or claim an action was completed, created, modified, or deleted unless a corresponding tool call actually executed and returned success=true in this turn.\n\n"
        )
        system_text += self.context_builder.format_context_prompt(self.session, query=latest_user_text, is_local=is_local)

        # Include daily plan if relevant
        lower = latest_user_text.lower()
        if "plan" in lower or "what should i work on" in lower or "today" in lower:
            system_text += "\n\n" + self.planner.format_plan_prompt(self.session)

        prompt_messages: list[dict[str, Any]] = [{"role": "system", "content": system_text}]

        # For local models, prune old history to the last 8-10 messages to keep context lean, fast, and prevent token overflow
        if is_local and len(db_messages) > 10:
            db_messages = db_messages[-10:]

        for m in db_messages:
            msg_dict: dict[str, Any] = {"role": m.role}
            if m.content:
                msg_dict["content"] = m.content
            if m.tool_calls:
                # Format OpenAI style tool_calls list
                tc_data = json.loads(m.tool_calls)
                msg_dict["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                    }
                    for tc in tc_data
                ]
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.name:
                msg_dict["name"] = m.name

            prompt_messages.append(msg_dict)

        return prompt_messages
