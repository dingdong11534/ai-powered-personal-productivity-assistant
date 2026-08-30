"""End-to-end integration tests for AI assistant memory tool interaction and context recall."""

from app.ai.assistant import AssistantCore
from app.conversations.schemas import ConversationCreate
from app.conversations.service import ConversationService
from app.memories.service import MemoryService
from app.storage.models import MemoryCategory


def test_ai_memory_tool_execution_and_recall_e2e(db_session):
    conv_svc = ConversationService(db_session)
    mem_svc = MemoryService(db_session)
    assistant = AssistantCore(db_session)

    # 1. Create conversation session
    conv = conv_svc.create_conversation(ConversationCreate(title="Memory E2E Test"))


    # 2. User tells assistant to remember preference
    msg1 = assistant.handle_user_message(
        conv.id,
        "Please remember that I prefer doing focused work in the evening.",
    )
    assert msg1 is not None

    # 3. Verify memory stored in SQLite database via tool execution
    mems = mem_svc.list_memories(category=MemoryCategory.PREFERENCE)
    assert len(mems) == 1
    assert "focused work in the evening" in mems[0].content
    mem_id = mems[0].id

    # 4. Ask assistant about preferences -> context builder injects memory
    msg2 = assistant.handle_user_message(conv.id, "What do you remember about my preferences?")
    assert msg2 is not None

    # 5. User tells assistant to forget the preference
    msg3 = assistant.handle_user_message(
        conv.id,
        f"Please forget my preference memory #{mem_id}.",
    )
    assert msg3 is not None

    # 6. Verify memory is archived in database
    active_mems = mem_svc.list_memories(include_archived=False)
    assert len(active_mems) == 0

    all_mems = mem_svc.list_memories(include_archived=True)
    assert len(all_mems) == 1
    assert all_mems[0].is_active is False
