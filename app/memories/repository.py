"""Repository layer for Memory SQLAlchemy operations."""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Memory, MemoryCategory


class MemoryRepository:
    """Handles raw database access for Memory entities."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        content: str,
        category: MemoryCategory,
        source_message_id: int | None = None,
        user_id: int | None = None,
    ) -> Memory:
        mem = Memory(
            content=content,
            category=category,
            source_message_id=source_message_id,
            is_active=True,
            user_id=user_id,
        )
        self.session.add(mem)
        self.session.commit()
        self.session.refresh(mem)
        return mem

    def get_by_id(self, memory_id: int) -> Memory | None:
        return self.session.get(Memory, memory_id)

    def list_memories(
        self,
        category: MemoryCategory | str | None = None,
        include_archived: bool = False,
        user_id: int | None = None,
    ) -> Sequence[Memory]:
        stmt = select(Memory)
        if not include_archived:
            stmt = stmt.where(Memory.is_active.is_(True))
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        stmt = stmt.order_by(Memory.created_at.desc())
        return self.session.scalars(stmt).all()

    def find_duplicate(
        self, category: MemoryCategory | str, content: str, user_id: int | None = None
    ) -> Memory | None:
        """Find an active memory with exact content match in category."""
        stmt = select(Memory).where(
            Memory.is_active.is_(True),
            Memory.category == category,
            Memory.content == content.strip(),
        )
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        return self.session.scalars(stmt).first()

    def search_memories(
        self,
        query: str,
        category: MemoryCategory | str | None = None,
        include_archived: bool = False,
        limit: int = 10,
        user_id: int | None = None,
    ) -> Sequence[Memory]:
        stmt = select(Memory)
        if not include_archived:
            stmt = stmt.where(Memory.is_active.is_(True))
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(Memory.content.ilike(like))
        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
        return self.session.scalars(stmt).all()


    def update(
        self,
        memory: Memory,
        content: str | None = None,
        category: MemoryCategory | None = None,
        is_active: bool | None = None,
    ) -> Memory:
        if content is not None:
            memory.content = content.strip()
        if category is not None:
            memory.category = category
        if is_active is not None:
            memory.is_active = is_active
        self.session.add(memory)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def delete(self, memory: Memory) -> None:
        """Hard delete a memory row from storage."""
        self.session.delete(memory)
        self.session.commit()
