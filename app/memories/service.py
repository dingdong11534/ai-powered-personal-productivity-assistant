"""Service layer for memory management, validation, duplicate prevention, and relevance retrieval."""

from typing import Sequence
from sqlalchemy.orm import Session

from app.memories.exceptions import DuplicateMemoryError, MemoryNotFoundError
from app.memories.repository import MemoryRepository
from app.memories.schemas import MemoryCreate, MemoryRead, MemoryUpdate
from app.storage.models import Memory, MemoryCategory


class MemoryService:
    """Manages memory creation, update, retrieval, duplicate checking, and relevance filtering."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = MemoryRepository(session)

    def create_memory(self, data: MemoryCreate) -> MemoryRead:
        clean_content = data.content.strip()
        # Duplicate check per category
        existing = self.repo.find_duplicate(data.category, clean_content)
        if existing:
            raise DuplicateMemoryError(data.category.value if hasattr(data.category, 'value') else str(data.category), clean_content)

        memory = self.repo.create(
            content=clean_content,
            category=data.category,
            source_message_id=data.source_message_id,
        )
        return MemoryRead.model_validate(memory)

    def get_memory(self, memory_id: int) -> MemoryRead:
        memory = self.repo.get_by_id(memory_id)
        if not memory:
            raise MemoryNotFoundError(memory_id)
        return MemoryRead.model_validate(memory)

    def list_memories(
        self,
        category: MemoryCategory | str | None = None,
        include_archived: bool = False,
    ) -> list[MemoryRead]:
        mems = self.repo.list_memories(category=category, include_archived=include_archived)
        return [MemoryRead.model_validate(m) for m in mems]

    def update_memory(self, memory_id: int, data: MemoryUpdate) -> MemoryRead:
        memory = self.repo.get_by_id(memory_id)
        if not memory:
            raise MemoryNotFoundError(memory_id)

        target_category = data.category or memory.category
        target_content = data.content.strip() if data.content else memory.content

        # If updating content or category, check for duplicates
        if (data.content is not None or data.category is not None) and (
            target_content != memory.content or target_category != memory.category
        ):
            dup = self.repo.find_duplicate(target_category, target_content)
            if dup and dup.id != memory.id:
                raise DuplicateMemoryError(
                    target_category.value if hasattr(target_category, 'value') else str(target_category),
                    target_content,
                )

        updated = self.repo.update(
            memory=memory,
            content=data.content,
            category=data.category,
            is_active=data.is_active,
        )
        return MemoryRead.model_validate(updated)

    def archive_memory(self, memory_id: int) -> MemoryRead:
        """Soft delete/archive a memory by setting is_active=False."""
        memory = self.repo.get_by_id(memory_id)
        if not memory:
            raise MemoryNotFoundError(memory_id)
        updated = self.repo.update(memory=memory, is_active=False)
        return MemoryRead.model_validate(updated)

    def delete_memory(self, memory_id: int) -> None:
        """Hard delete a memory row."""
        memory = self.repo.get_by_id(memory_id)
        if not memory:
            raise MemoryNotFoundError(memory_id)
        self.repo.delete(memory)

    def retrieve_relevant_memories(
        self,
        query: str | None = None,
        category: MemoryCategory | str | None = None,
        limit: int = 5,
    ) -> list[MemoryRead]:
        """Retrieve active memories filtered by category and simple relevance keyword matching."""
        if not query:
            # Return most recent active memories up to limit
            mems = self.repo.list_memories(category=category, include_archived=False)[:limit]
            return [MemoryRead.model_validate(m) for m in mems]

        clean_query = query.strip()
        # Strategy 1: Search substring/keyword match
        mems = list(self.repo.search_memories(query=clean_query, category=category, include_archived=False, limit=limit))

        # Strategy 2: If query has multiple words, match individual significant terms if search results < limit
        if len(mems) < limit and " " in clean_query:
            words = [w for w in clean_query.lower().split() if len(w) > 3 and w not in ("that", "this", "with", "from", "have", "what", "remember", "forget", "about", "prefer", "work")]
            existing_ids = {m.id for m in mems}
            for w in words:
                if len(mems) >= limit:
                    break
                extra = self.repo.search_memories(query=w, category=category, include_archived=False, limit=limit)
                for em in extra:
                    if em.id not in existing_ids and len(mems) < limit:
                        mems.append(em)
                        existing_ids.add(em.id)

        return [MemoryRead.model_validate(m) for m in mems]
