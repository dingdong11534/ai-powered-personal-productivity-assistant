"""Unit tests for Memory AI Tools execution."""

from app.ai.tools.implementations import (
    DeleteMemoryTool,
    ListMemoriesTool,
    RememberInformationTool,
    SearchMemoriesTool,
    UpdateMemoryTool,
    get_default_tool_registry,
)
from app.memories.service import MemoryService


def test_remember_information_tool(db_session):
    registry = get_default_tool_registry()
    tool = registry.get_tool("remember_information")
    assert tool is not None
    assert tool.name == "remember_information"

    result = registry.execute_tool(
        "remember_information",
        {"content": "User prefers night work", "category": "preference"},
        db_session,
    )
    assert result["success"] is True
    assert result["data"]["content"] == "User prefers night work"
    assert result["data"]["category"] == "preference"


def test_list_and_search_memories_tools(db_session):
    registry = get_default_tool_registry()
    svc = MemoryService(db_session)
    from app.memories.schemas import MemoryCreate
    from app.storage.models import MemoryCategory

    svc.create_memory(MemoryCreate(content="Goal is to ship Phase 5", category=MemoryCategory.GOAL))

    # List tool
    list_res = registry.execute_tool("list_memories", {}, db_session)
    assert list_res["success"] is True
    assert len(list_res["data"]["memories"]) == 1

    # Search tool
    search_res = registry.execute_tool("search_memories", {"query": "Phase 5"}, db_session)
    assert search_res["success"] is True
    assert len(search_res["data"]["memories"]) == 1


def test_update_and_delete_memory_tools(db_session):
    registry = get_default_tool_registry()
    rem_res = registry.execute_tool(
        "remember_information",
        {"content": "Routine: 30 min morning exercise", "category": "routine"},
        db_session,
    )
    mem_id = rem_res["data"]["id"]

    # Update tool
    upd_res = registry.execute_tool(
        "update_memory",
        {"memory_id": mem_id, "content": "Routine: 45 min morning workout"},
        db_session,
    )
    assert upd_res["success"] is True
    assert upd_res["data"]["content"] == "Routine: 45 min morning workout"

    # Delete tool (archive)
    del_res = registry.execute_tool("delete_memory", {"memory_id": mem_id}, db_session)
    assert del_res["success"] is True
    assert del_res["data"]["is_active"] is False
