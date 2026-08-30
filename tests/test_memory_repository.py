"""Unit tests for MemoryRepository."""

from app.memories.repository import MemoryRepository
from app.storage.models import MemoryCategory


def test_create_and_get_memory(db_session):
    repo = MemoryRepository(db_session)
    mem = repo.create(content="User prefers dark mode UI.", category=MemoryCategory.PREFERENCE)
    assert mem.id is not None
    assert mem.content == "User prefers dark mode UI."
    assert mem.category == MemoryCategory.PREFERENCE
    assert mem.is_active is True

    fetched = repo.get_by_id(mem.id)
    assert fetched is not None
    assert fetched.id == mem.id


def test_list_and_search_memories(db_session):
    repo = MemoryRepository(db_session)
    repo.create(content="User works evening shift.", category=MemoryCategory.ROUTINE)
    repo.create(content="Main project is Personal Productivity Assistant.", category=MemoryCategory.PROJECT_CONTEXT)
    archived_mem = repo.create(content="Archived note.", category=MemoryCategory.PREFERENCE)
    repo.update(archived_mem, is_active=False)

    active_mems = repo.list_memories(include_archived=False)
    assert len(active_mems) == 2

    all_mems = repo.list_memories(include_archived=True)
    assert len(all_mems) == 3

    search_res = repo.search_memories(query="evening")
    assert len(search_res) == 1
    assert search_res[0].content == "User works evening shift."



def test_find_duplicate(db_session):
    repo = MemoryRepository(db_session)
    repo.create(content="User studies at night.", category=MemoryCategory.ROUTINE)
    dup = repo.find_duplicate(MemoryCategory.ROUTINE, "User studies at night.")
    assert dup is not None

    no_dup = repo.find_duplicate(MemoryCategory.PREFERENCE, "User studies at night.")
    assert no_dup is None
