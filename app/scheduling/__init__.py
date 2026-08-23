"""
Schedule (calendar block) domain logic.

exceptions.py  - ScheduleItemNotFoundError, InvalidTimeRangeError.
schemas.py     - Pydantic schemas: create/update/read.
repository.py  - ScheduleItemRepository: direct CRUD + overlap query.
service.py     - ScheduleService: owns time-range validation and
                  conflict *detection* (not blocking — see that
                  module's docstring for why).

Its own top-level package covering ScheduleItem only — Pomodoro and
Reminders each got their own package too (see app.pomodoro's package
docstring for why), rather than one "scheduling" package covering all
three as an earlier placeholder here once suggested.
"""
