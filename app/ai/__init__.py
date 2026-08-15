"""
AI abstraction layer — implemented starting Phase 4.

Will contain: a provider-agnostic LLM client interface (so OpenAI-
compatible, Anthropic-compatible, Groq, or a local Ollama model can be
swapped via configuration), structured tool/function definitions, and the
tool-calling loop that AssistantCore.handle_message() delegates to.

Hard rule carried over from the project spec: this layer requests actions
via structured tool calls only. It never executes arbitrary AI-generated
code or shell commands, and every tool call it makes still passes through
app.core.permissions before touching data.
"""
