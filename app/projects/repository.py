"""
ProjectRepository — direct, ORM-level CRUD against the `projects` table.

Same shape and reasoning as app.tasks.repository.TaskRepository: dumb,
no business rules, everything beyond "read/write a row" lives in
ProjectService. See that module's docstring for the layering rationale.

There is deliberately no `delete()` method here — the Project API never
exposes a hard delete (see ProjectService), so there's no caller for one.
Adding it "for completeness" would be exactly the kind of premature
feature the project brief asks to avoid.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Project


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, project: Project) -> Project:
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get(self, project_id: int) -> Project | None:
        return self.db.get(Project, project_id)

    def list(self, *, skip: int = 0, limit: int = 100, include_archived: bool = True) -> list[Project]:
        stmt = select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit)
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        return list(self.db.scalars(stmt))

    def update(self, project: Project, changes: dict) -> Project:
        for field, value in changes.items():
            setattr(project, field, value)
        self.db.commit()
        self.db.refresh(project)
        return project
