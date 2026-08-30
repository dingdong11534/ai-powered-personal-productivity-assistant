"""Domain exceptions for memory operations."""


class MemoryError(Exception):
    """Base exception for all memory domain errors."""


class MemoryNotFoundError(MemoryError):
    """Raised when a requested memory ID does not exist."""

    def __init__(self, memory_id: int):
        self.memory_id = memory_id
        super().__init__(f"Memory #{memory_id} not found.")


class DuplicateMemoryError(MemoryError):
    """Raised when attempting to add an identical memory content within the same category."""

    def __init__(self, category: str, content: str):
        self.category = category
        self.content = content
        super().__init__(f"Duplicate memory already exists in category '{category}': '{content}'.")
