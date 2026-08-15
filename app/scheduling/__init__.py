"""
Scheduling, reminders, and Pomodoro/focus-session logic — implemented in
Phase 2.

Kept separate from app.tasks because scheduling concerns (when/how often)
are a distinct axis from task content (what/why), and several entities
here (ScheduleItem, Reminder, PomodoroSession) aren't tasks at all.
"""
