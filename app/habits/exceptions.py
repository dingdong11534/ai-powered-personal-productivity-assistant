"""
Habit domain exceptions. Plain Python exceptions, not `HTTPException` —
same reasoning as every other domain package's exceptions.py: no
dependency on FastAPI here. Translated to HTTP responses in
app/interfaces/main.py.
"""

from __future__ import annotations

from datetime import date


class HabitNotFoundError(Exception):
    """Raised when a habit lookup by id finds nothing."""

    def __init__(self, habit_id: int) -> None:
        self.habit_id = habit_id
        super().__init__(f"Habit {habit_id} not found")


class ArchivedHabitError(Exception):
    """Raised when trying to record a completion for an archived habit.

    Mirrors ArchivedProjectError's reasoning: archiving blocks *new*
    activity but never touches existing history. An archived habit can
    still be read, and its past completions/statistics remain fully
    accessible — only `record_completion` is blocked.
    """

    def __init__(self, habit_id: int) -> None:
        self.habit_id = habit_id
        super().__init__(f"Habit {habit_id} is archived")


class DuplicateCompletionError(Exception):
    """Raised when a habit already has a completion recorded for the
    given calendar date."""

    def __init__(self, habit_id: int, completed_date: date) -> None:
        self.habit_id = habit_id
        self.completed_date = completed_date
        super().__init__(
            f"Habit {habit_id} already has a completion recorded for {completed_date}"
        )
