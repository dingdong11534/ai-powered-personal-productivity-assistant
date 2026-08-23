"""
Pomodoro/focus-session domain logic.

exceptions.py  - PomodoroSessionNotFoundError, SessionAlreadyEndedError.
schemas.py     - Pydantic schemas: session start/end/read.
repository.py  - PomodoroSessionRepository: direct CRUD.
service.py     - PomodoroSessionService: owns "can't end an
                 already-ended session" and optional task-existence
                 validation.

Same layering as every other domain package — see app.tasks's package
docstring. This is its own top-level package rather than folded into a
single "scheduling" package covering Pomodoro+Reminders+ScheduleItem
(as an earlier placeholder in this file once suggested): the Phase 2
brief asks for four independent route groups
(`/pomodoro`, `/reminders`, `/schedule`, `/notifications`), and giving
each its own domain package mirrors that separation and matches the
one-package-per-resource pattern already established by
app.projects/app.habits, rather than growing one package to cover three
unrelated aggregates.
"""
