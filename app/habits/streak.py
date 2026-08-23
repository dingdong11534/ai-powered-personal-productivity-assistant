"""
Streak and statistics calculation — pure functions, no database.

WHAT THIS DOES
---------------
Computes a habit's current streak and summary statistics from a plain
list of completion dates. Takes `today` as an explicit argument rather
than calling `date.today()` internally, which is what makes this fully
unit-testable without mocking the clock (see tests/test_habit_streak.py)
and is why it lives in its own module instead of inline in
`HabitService`: this is pure, deterministic logic with no I/O, and
keeping it separate means it can be tested directly, fast, without a
database at all.

WHY "THE COMPLETION HISTORY IS AUTHORITATIVE" MATTERS HERE
-----------------------------------------------------------------
Nothing in this project stores a "current streak" number anywhere. Every
call to `calculate_streak` walks the actual `HabitCompletion` rows (via
`HabitService`, which fetches them and passes the dates in). That means
a streak can never drift out of sync with reality — there's no cached
counter to forget to update, and no risk of double-counting or
under-counting from a missed increment. The cost is recomputing from
scratch on every read, which is the right trade for a single local
user's data volume.

THE ALGORITHM
---------------
A habit's timeline is divided into periods based on its frequency
(a calendar day, an ISO week, or a calendar month — see `_period_key`).
A period is "satisfied" if it has at least `target_count` completions
in it. The current streak is the number of *consecutive* satisfied
periods, walking backward from today's period — with one exception:
today's own period is allowed to be unsatisfied without breaking the
streak, since it may simply not be finished yet (you haven't gone to
bed yet). Every period before today's must be satisfied, or the streak
stops there. This matches how habit trackers conventionally work: doing
today's habit "keeps the streak going", but *not having done it yet*
today doesn't retroactively erase yesterday's progress.

Verified against several scenarios (consecutive days, a gap breaking the
streak, today-not-done-yet not breaking it, weekly/monthly periods,
a year-boundary month rollover) before being wired into HabitService —
see tests/test_habit_streak.py for the same cases as automated tests.

HOW TO TEST
------------
tests/test_habit_streak.py — no fixtures, no database; every test just
calls these functions directly with plain lists of `date` objects.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from app.storage.models import HabitFrequency


def _period_key(frequency: HabitFrequency, d: date):
    """A hashable key identifying which period `d` falls into."""
    if frequency == HabitFrequency.DAILY:
        return d
    if frequency == HabitFrequency.WEEKLY:
        iso_year, iso_week, _ = d.isocalendar()
        return (iso_year, iso_week)
    if frequency == HabitFrequency.MONTHLY:
        return (d.year, d.month)
    raise ValueError(f"Unknown frequency: {frequency!r}")  # pragma: no cover


def _previous_period_key(frequency: HabitFrequency, key):
    """The key for the period immediately before `key`."""
    if frequency == HabitFrequency.DAILY:
        return key - timedelta(days=1)
    if frequency == HabitFrequency.WEEKLY:
        year, week = key
        monday = date.fromisocalendar(year, week, 1)
        prev_monday = monday - timedelta(days=7)
        iso_year, iso_week, _ = prev_monday.isocalendar()
        return (iso_year, iso_week)
    if frequency == HabitFrequency.MONTHLY:
        year, month = key
        return (year - 1, 12) if month == 1 else (year, month - 1)
    raise ValueError(f"Unknown frequency: {frequency!r}")  # pragma: no cover


def calculate_streak(
    frequency: HabitFrequency,
    target_count: int,
    completion_dates: list[date],
    today: date,
) -> int:
    """Return the current consecutive-period streak. See module
    docstring for the algorithm and the "today doesn't break it" rule."""
    counts = Counter(_period_key(frequency, d) for d in completion_dates)
    streak = 0
    key = _period_key(frequency, today)
    is_current_period = True
    while True:
        if counts.get(key, 0) >= target_count:
            streak += 1
        elif not is_current_period:
            break
        is_current_period = False
        key = _previous_period_key(frequency, key)
    return streak


@dataclass(frozen=True)
class HabitStatistics:
    """Summary statistics for a habit, computed from its completion
    history — see module docstring."""

    total_completions: int
    current_streak: int
    longest_streak: int
    periods_since_creation: int
    periods_satisfied: int
    completion_rate: float  # periods_satisfied / periods_since_creation, 0.0 if none elapsed yet


def calculate_statistics(
    frequency: HabitFrequency,
    target_count: int,
    completion_dates: list[date],
    created_date: date,
    today: date,
) -> HabitStatistics:
    """Compute total completions, current streak, longest streak, and a
    completion rate over every period from the habit's creation through
    today (inclusive).

    `longest_streak` scans every period from `created_date` to `today`
    rather than just the current run — a habit whose long-ago streak
    beat its current one should still be able to report that.
    """
    if today < created_date:
        # Defensive: in normal use `today` is "now" and a habit's
        # creation is always in the past relative to that, so this
        # shouldn't occur — but without this guard, the backward walk
        # below would never reach `created_date` and loop forever.
        # Clamping treats "before the habit existed" as "day one".
        today = created_date

    counts = Counter(_period_key(frequency, d) for d in completion_dates)

    created_key = _period_key(frequency, created_date)
    period_keys: list = []
    key = _period_key(frequency, today)
    while True:
        period_keys.append(key)
        if key == created_key:
            break
        key = _previous_period_key(frequency, key)
    period_keys.reverse()  # oldest first

    satisfied_flags = [counts.get(k, 0) >= target_count for k in period_keys]
    periods_satisfied = sum(satisfied_flags)
    periods_since_creation = len(period_keys)

    longest_streak = 0
    current_run = 0
    for satisfied in satisfied_flags:
        if satisfied:
            current_run += 1
            longest_streak = max(longest_streak, current_run)
        else:
            current_run = 0

    completion_rate = (
        periods_satisfied / periods_since_creation if periods_since_creation else 0.0
    )

    return HabitStatistics(
        total_completions=len(completion_dates),
        current_streak=calculate_streak(frequency, target_count, completion_dates, today),
        longest_streak=longest_streak,
        periods_since_creation=periods_since_creation,
        periods_satisfied=periods_satisfied,
        completion_rate=completion_rate,
    )
