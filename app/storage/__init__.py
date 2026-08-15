"""
Persistence layer.

database.py  - SQLAlchemy engine/session setup, the declarative Base, and
               the get_db() dependency every request-scoped session comes
               from.
models.py    - SQLAlchemy ORM models (Task, and future entities from
               docs/architecture.md's schema proposal).

Domain packages (app.tasks, app.habits, ...) depend on this package for
persistence; this package must not depend on them, or on app.interfaces —
keeping the dependency direction one-way is what allows the storage
backend to change without touching business logic.

Migrations: table creation currently goes through
`Base.metadata.create_all()` (see database.create_all_tables), which is
fine for a single-developer, pre-release project with no production data
to preserve. Alembic (already listed, commented out, in requirements.txt)
gets introduced the moment a schema change needs to preserve existing
data — i.e. as soon as this project has a database anyone cares about
not wiping. Introducing Alembic before that point would be adding
migration-authoring overhead with nothing yet worth migrating.
"""
