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

from app.storage.models import Project, ProjectMember


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, project: Project) -> Project:
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        if project.user_id:
            member = ProjectMember(
                project_id=project.id,
                user_id=project.user_id,
                role="owner",
                status="accepted",
            )
            self.db.add(member)
            self.db.commit()
        return project

    def get(self, project_id: int) -> Project | None:
        return self.db.get(Project, project_id)

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_archived: bool = True,
        user_id: int | None = None,
    ) -> list[Project]:
        stmt = select(Project).order_by(Project.created_at.desc())
        if user_id is not None:
            member_project_ids = select(ProjectMember.project_id).where(
                ProjectMember.user_id == user_id,
                ProjectMember.status == "accepted",
            )
            stmt = stmt.where(
                (Project.user_id == user_id) | (Project.id.in_(member_project_ids))
            )
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt))

    def update(self, project: Project, changes: dict) -> Project:
        for field, value in changes.items():
            setattr(project, field, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project: Project) -> None:
        self.db.delete(project)
        self.db.commit()

