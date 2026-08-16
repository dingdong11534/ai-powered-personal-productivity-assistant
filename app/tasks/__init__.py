"""
Task domain logic.

exceptions.py           - domain-specific exceptions (TaskNotFoundError,
                          TagNotFoundError, DuplicateTagError,
                          SelfDependencyError, DependencyCycleError,
                          DuplicateDependencyError, UnresolvedDependencyError),
                          raised by the service layer and translated to
                          HTTP responses in app.interfaces.
schemas.py              - Pydantic schemas for the API boundary: Task
                          create/update/read, Tag create/read, and
                          TaskDependency create/read.
repository.py           - TaskRepository: thin, direct CRUD + filtering
                          against the `tasks` table.
service.py              - TaskService: the layer app.interfaces calls.
                          Owns business rules (project validation,
                          dependency-blocked completion) and raises
                          domain exceptions; delegates persistence to
                          TaskRepository.
tag_repository.py       - TagRepository: direct access to `tags` and the
                          `task_tags` association table.
tag_service.py          - TagService: tag uniqueness, idempotent
                          attach/detach.
dependency_repository.py - TaskDependencyRepository: direct access to
                          `task_dependencies`.
dependency_service.py   - TaskDependencyService: self-dependency
                          rejection, cycle detection, and the query
                          TaskService uses to block completion.

No FastAPI routes and no raw SQL/session-juggling belong in this package
directly — routes live in app.interfaces, and every class here only ever
receives an already-open `Session` (via its constructor), it never
creates one itself. That's what keeps this package testable without
spinning up FastAPI and reusable from a future CLI or from voice without
modification.

Splitting tags and dependencies into their own repository/service pairs,
rather than growing TaskRepository/TaskService to cover everything, is a
deliberate choice: each class stays focused on one concern, instead of
becoming the kind of do-everything manager class the project brief asks
to avoid. TaskService composes the others (via their repositories) where
a cross-cutting rule genuinely belongs to Task — see that module's
docstring.
"""
