"""Assistant Core Engine orchestrating message flow, context, tool execution, and response synthesis."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.ai.context import ContextBuilder
from app.ai.planner import DailyPlanner
from app.ai.provider import AIProvider, get_ai_provider
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
    ):
        self.session = session
        self.provider = provider or get_ai_provider()
        self.tool_registry = tool_registry or get_default_tool_registry()
        self.conv_svc = ConversationService(session)
        self.context_builder = ContextBuilder()
        self.planner = DailyPlanner()

    def handle_user_message(self, conversation_id: int, user_content: str) -> MessageRead:
        # 1. Save user message to database
        self.conv_svc.add_message(
            conversation_id,
            MessageCreate(role="user", content=user_content),
        )

        # 2. Bounded execution loop (max 5 iterations)
        max_iterations = 5
        for _ in range(max_iterations):
            # Load fresh history and format for LLM
            db_messages = self.conv_svc.get_messages(conversation_id)
            formatted_messages = self._build_prompt_messages(db_messages, user_content)

            tool_schemas = self.tool_registry.get_tools_schema()
            response = self.provider.generate(formatted_messages, tools=tool_schemas)

            # If no tool calls requested, record assistant message and finish
            if not response.tool_calls:
                content = response.content or "Task completed."
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
                exec_result = self.tool_registry.execute_tool(tc.name, tc.arguments, self.session)
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

    def _build_prompt_messages(
        self, db_messages: list[MessageRead], latest_user_text: str
    ) -> list[dict[str, Any]]:
        system_text = (
            "You are an AI Personal Productivity Assistant. "
            "You help the user manage tasks, projects, habits, schedules, reminders, pomodoro focus sessions, and notifications. "
            "Execute tools whenever requested by the user. Do not invent fake state.\n\n"
        )
        system_text += self.context_builder.format_context_prompt(self.session, query=latest_user_text)

        # Include daily plan if relevant
        lower = latest_user_text.lower()
        if "plan" in lower or "what should i work on" in lower or "today" in lower:
            system_text += "\n\n" + self.planner.format_plan_prompt(self.session)

        prompt_messages: list[dict[str, Any]] = [{"role": "system", "content": system_text}]

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
