"""Unit tests for MemoryService."""

import pytest
from app.memories.exceptions import DuplicateMemoryError, MemoryNotFoundError
from app.memories.schemas import MemoryCreate, MemoryUpdate
from app.memories.service import MemoryService
from app.storage.models import MemoryCategory


def test_memory_service_crud(db_session):
    svc = MemoryService(db_session)
    create_data = MemoryCreate(
        content="Prefer working in the evening",
        category=MemoryCategory.PREFERENCE,
    )
    mem = svc.create_memory(create_data)
    assert mem.id is not None
    assert mem.content == "Prefer working in the evening"
    assert mem.category == MemoryCategory.PREFERENCE

    # Get memory
    fetched = svc.get_memory(mem.id)
    assert fetched.id == mem.id

    # Update memory
    updated = svc.update_memory(mem.id, MemoryUpdate(content="Prefer focused work late at night"))
    assert updated.content == "Prefer focused work late at night"

    # Archive memory
    archived = svc.archive_memory(mem.id)
    assert archived.is_active is False

    # Delete memory
    svc.delete_memory(mem.id)
    with pytest.raises(MemoryNotFoundError):
        svc.get_memory(mem.id)


def test_memory_service_duplicate_prevention(db_session):
    svc = MemoryService(db_session)
    svc.create_memory(MemoryCreate(content="Duplicate test content", category=MemoryCategory.GOAL))

    with pytest.raises(DuplicateMemoryError):
        svc.create_memory(MemoryCreate(content="  Duplicate test content  ", category=MemoryCategory.GOAL))


def test_retrieve_relevant_memories(db_session):
    svc = MemoryService(db_session)
    svc.create_memory(MemoryCreate(content="User prefers night focus blocks.", category=MemoryCategory.PREFERENCE))
    svc.create_memory(MemoryCreate(content="User goal is to finish Phase 5.", category=MemoryCategory.GOAL))
    svc.create_memory(MemoryCreate(content="User is building Personal Productivity Assistant.", category=MemoryCategory.PROJECT_CONTEXT))

    # Relevance search
    results = svc.retrieve_relevant_memories(query="night focus")
    assert len(results) >= 1
    assert "night focus" in results[0].content

    # Category filtered retrieval
    pref_results = svc.retrieve_relevant_memories(category=MemoryCategory.PREFERENCE)
    assert len(pref_results) == 1
    assert pref_results[0].category == MemoryCategory.PREFERENCE
