"""
Reminder domain logic.

exceptions.py  - ReminderNotFoundError.
schemas.py     - Pydantic schemas: create/update/read.
repository.py  - ReminderRepository: direct CRUD + due/upcoming queries.
service.py     - ReminderService: owns idempotent firing and the
                  optional task-existence check.

Its own top-level package rather than folded into a single "scheduling"
package — see app.pomodoro's package docstring for the same reasoning,
which applies here too.
"""
