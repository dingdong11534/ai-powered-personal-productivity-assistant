"""
Habit domain logic.

exceptions.py  - HabitNotFoundError, ArchivedHabitError,
                 DuplicateCompletionError.
schemas.py     - Pydantic schemas: Habit create/update/read, completion
                 create/read, and a statistics response.
repository.py  - HabitRepository (CRUD on `habits`) and
                 HabitCompletionRepository (CRUD on `habit_completions`)
                 — two small classes in one file since they're two
                 tables of a single aggregate (a Habit and its own
                 completion log), unlike Tag, which is an independent
                 resource with its own top-level API and so got its own
                 file in app.tasks.
service.py     - HabitService: the layer app.interfaces calls. Owns
                 archived-habit and duplicate-completion rules, and
                 delegates streak/statistics computation to streak.py.
streak.py      - Pure functions (no database) for computing a habit's
                 current streak and summary statistics from its
                 completion history. See that module's docstring for
                 why the completion history — not a stored counter — is
                 the source of truth.

Same layering and "no FastAPI/raw SQL in this package" rules as
app.tasks and app.projects — see their package docstrings.
"""
