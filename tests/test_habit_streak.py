"""Tests for app.habits.streak — pure functions, no database, no
fixtures. Every test constructs plain `date` objects and calls
`calculate_streak`/`calculate_statistics` directly.

Run with: pytest tests/test_habit_streak.py -v

These scenarios were verified against a standalone prototype before this
file existed, then re-verified against the actual module — see the
project's implementation notes.
"""

from datetime import date, timedelta

from app.habits.streak import calculate_statistics, calculate_streak
from app.storage.models import HabitFrequency

TODAY = date(2026, 8, 16)  # a Sunday


def test_daily_consecutive_streak():
    dates = [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert calculate_streak(HabitFrequency.DAILY, 1, dates, TODAY) == 3


def test_daily_today_not_done_yet_does_not_break_streak():
    dates = [TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert calculate_streak(HabitFrequency.DAILY, 1, dates, TODAY) == 2


def test_daily_gap_breaks_streak():
    dates = [TODAY, TODAY - timedelta(days=2)]  # missing yesterday
    assert calculate_streak(HabitFrequency.DAILY, 1, dates, TODAY) == 1


def test_daily_no_completions_is_zero_streak():
    assert calculate_streak(HabitFrequency.DAILY, 1, [], TODAY) == 0


def test_daily_missed_today_and_yesterday_is_zero_streak():
    dates = [TODAY - timedelta(days=5)]
    assert calculate_streak(HabitFrequency.DAILY, 1, dates, TODAY) == 0


def test_weekly_streak_with_target_met_each_week():
    this_week = [TODAY, TODAY - timedelta(days=1)]
    last_week = [TODAY - timedelta(days=7), TODAY - timedelta(days=8)]
    assert calculate_streak(HabitFrequency.WEEKLY, 2, this_week + last_week, TODAY) == 2


def test_weekly_streak_counts_satisfied_past_week_even_if_current_incomplete():
    this_week = [TODAY, TODAY - timedelta(days=1)]  # only 2, target is 3
    last_week = [
        TODAY - timedelta(days=7),
        TODAY - timedelta(days=8),
        TODAY - timedelta(days=9),
    ]  # 3, satisfied
    dates = this_week + last_week
    assert calculate_streak(HabitFrequency.WEEKLY, 3, dates, TODAY) == 1


def test_monthly_streak_across_two_months():
    this_month = date(2026, 8, 5)
    last_month = date(2026, 7, 5)
    assert calculate_streak(HabitFrequency.MONTHLY, 1, [this_month, last_month], TODAY) == 2


def test_monthly_streak_across_year_boundary():
    jan = date(2026, 1, 10)
    dec_prev_year = date(2025, 12, 10)
    assert calculate_streak(HabitFrequency.MONTHLY, 1, [jan, dec_prev_year], jan) == 2


def test_statistics_full_streak():
    created = TODAY - timedelta(days=4)
    dates = [TODAY - timedelta(days=i) for i in range(5)]
    stats = calculate_statistics(HabitFrequency.DAILY, 1, dates, created, TODAY)

    assert stats.total_completions == 5
    assert stats.current_streak == 5
    assert stats.longest_streak == 5
    assert stats.periods_since_creation == 5
    assert stats.periods_satisfied == 5
    assert stats.completion_rate == 1.0


def test_statistics_with_a_gap():
    created = TODAY - timedelta(days=5)
    dates = [TODAY, TODAY - timedelta(days=2), TODAY - timedelta(days=3)]
    stats = calculate_statistics(HabitFrequency.DAILY, 1, dates, created, TODAY)

    assert stats.total_completions == 3
    assert stats.current_streak == 1  # only today, before hitting yesterday's gap
    assert stats.longest_streak == 2  # the two-in-a-row run
    assert stats.periods_since_creation == 6
    assert stats.periods_satisfied == 3
    assert abs(stats.completion_rate - 0.5) < 1e-9


def test_statistics_habit_created_today_with_no_completions():
    stats = calculate_statistics(HabitFrequency.DAILY, 1, [], TODAY, TODAY)

    assert stats.periods_since_creation == 1
    assert stats.periods_satisfied == 0
    assert stats.current_streak == 0
    assert stats.completion_rate == 0.0


def test_statistics_guards_against_today_before_created_date():
    """Defensive: today < created_date should never infinite-loop; it's
    clamped to treat created_date as day one."""
    future_created = TODAY + timedelta(days=10)
    stats = calculate_statistics(HabitFrequency.DAILY, 1, [], future_created, TODAY)

    assert stats.periods_since_creation == 1
    assert stats.completion_rate == 0.0
