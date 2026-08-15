"""
Task domain logic.

exceptions.py  - domain-specific exceptions (TaskNotFoundError), raised by
                 the service layer and translated to HTTP responses in
                 app.interfaces.
schemas.py     - Pydantic schemas for the API boundary: what a client may
                 send to create/update a task, and what the API returns.
                 These are NOT the same classes as the SQLAlchemy model in
                 app.storage.models — see schemas.py's docstring for why.
repository.py  - TaskRepository: thin, direct CRUD against the `tasks`
                 table. No business rules.
service.py     - TaskService: the layer app.interfaces actually calls.
                 Owns business rules and raises domain exceptions;
                 delegates persistence to TaskRepository.

No FastAPI routes and no raw SQL/session-juggling belong in this package
directly — routes live in app.interfaces, and this package only ever
receives an already-open `Session` (via TaskService's constructor), it
never creates one itself. That's what keeps this package testable without
spinning up FastAPI (see tests/test_task_service.py) and reusable from a
future CLI or from voice without modification.

Project/tag/dependency logic (originally scoped for "Phase 1" broadly)
will be added here once app.storage.models grows those tables — Phase 0.2
covers Task in isolation only.
"""
