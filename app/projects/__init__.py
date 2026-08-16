"""
Project domain logic.

exceptions.py  - ProjectNotFoundError, ArchivedProjectError.
schemas.py     - Pydantic schemas for the API boundary (ProjectCreate,
                 ProjectUpdate, ProjectRead).
repository.py  - ProjectRepository: thin, direct CRUD against the
                 `projects` table.
service.py     - ProjectService: the layer app.interfaces calls; owns
                 the "no hard delete, only archive" rule.

Mirrors app.tasks's internal layering (repository vs. service) for the
same reasons — see app/tasks/__init__.py.

Kept as its own top-level package rather than folded into app.tasks:
Project is its own aggregate with its own lifecycle (create / update /
archive), not merely an attribute of Task. app.tasks is allowed to depend
on app.projects (to validate a task's project_id — see
app.tasks.service), since both are domain packages with no dependency on
app.interfaces; app.projects must never depend on app.tasks.
"""
