"""
Project API routes.

Same thin-route discipline as app.interfaces.api.tasks: parse input,
call one ProjectService method, return the result.

No DELETE /projects/{id} route — this API never exposes a hard delete
for projects (see ProjectService). `POST /projects/{id}/archive` is the
only lifecycle-ending action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import check_item_access, get_current_user
from app.projects.schemas import (
    ProjectCreate,
    ProjectInviteCreate,
    ProjectInviteRead,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
)
from app.projects.service import ProjectService
from app.storage.database import get_db
from app.storage.models import Project, ProjectMember, User


router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    return service.create_project(data, user_id=current_user.id)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    include_archived: bool = Query(
        default=True, description="Set to false to exclude archived projects."
    ),
    all_users: bool = Query(default=False, description="Admin only: list projects across all users."),
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    return service.list_projects(
        skip=skip,
        limit=limit,
        include_archived=include_archived,
        user_id=target_user_id,
    )


def check_project_access_or_membership(
    project: Project,
    current_user: User,
    session: Session,
    action: str = "access",
) -> None:
    if current_user.role == "admin":
        return
    if project.user_id == current_user.id:
        return
    # Check if user is an accepted member
    member = session.query(ProjectMember).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == current_user.id,
        ProjectMember.status == "accepted",
    ).first()
    if member:
        return
    from fastapi import HTTPException
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied: You cannot {action} this project.",
    )



@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    project = service.get_project(project_id)
    check_project_access_or_membership(project, current_user, session, "view")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    project = service.get_project(project_id)
    check_project_access_or_membership(project, current_user, session, "modify")
    return service.update_project(project_id, data)


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    project = service.get_project(project_id)
    check_project_access_or_membership(project, current_user, session, "archive")
    return service.archive_project(project_id)


@router.post("/{project_id}/unarchive", response_model=ProjectRead)
def unarchive_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    project = service.get_project(project_id)
    check_project_access_or_membership(project, current_user, session, "unarchive")
    return service.unarchive_project(project_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> Response:
    project = service.get_project(project_id)
    check_item_access(project.user_id, current_user, "delete")
    service.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------
# Collaboration & Member Endpoints
# -------------------------------------------------------------

@router.get("/invites/pending", response_model=list[ProjectInviteRead])
def list_pending_invites(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[ProjectInviteRead]:
    """List pending project invitations for the current user."""
    members = session.query(ProjectMember).filter(
        ProjectMember.user_id == current_user.id,
        ProjectMember.status == "pending",
    ).all()
    results = []
    for m in members:
        p = session.get(Project, m.project_id)
        if not p:
            continue
        inviter = session.get(User, m.invited_by_id) if m.invited_by_id else None
        results.append(
            ProjectInviteRead(
                id=m.id,
                project_id=p.id,
                project_name=p.name,
                project_color=p.color,
                invited_by_id=inviter.id if inviter else None,
                invited_by_name=inviter.username if inviter else "Unknown",
                status=m.status,
                created_at=m.created_at,
            )
        )
    return results


@router.post("/invites/{invite_id}/accept")
def accept_project_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Accept an invitation to join a project."""
    member = session.get(ProjectMember, invite_id)
    if not member or member.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    member.status = "accepted"
    session.commit()

    # Notify inviter / project owner
    project = session.get(Project, member.project_id)
    target_notify = member.invited_by_id or (project.user_id if project else None)
    if target_notify and target_notify != current_user.id:
        from app.notifications.schemas import NotificationCreate
        from app.notifications.service import NotificationService
        NotificationService(session).create_notification(
            NotificationCreate(
                title="Project Invite Accepted",
                message=f"User {current_user.username} (ID: #{current_user.id}) joined project '{project.name if project else 'Project'}'.",
            ),
            user_id=target_notify,
        )

    return {"status": "ok", "message": "Joined project successfully"}


@router.post("/invites/{invite_id}/reject")
def reject_project_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Decline an invitation to join a project."""
    member = session.get(ProjectMember, invite_id)
    if not member or member.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    member.status = "rejected"
    session.commit()

    # Notify inviter
    project = session.get(Project, member.project_id)
    if member.invited_by_id and member.invited_by_id != current_user.id:
        from app.notifications.schemas import NotificationCreate
        from app.notifications.service import NotificationService
        NotificationService(session).create_notification(
            NotificationCreate(
                title="Project Invite Declined",
                message=f"User {current_user.username} (ID: #{current_user.id}) declined invite to project '{project.name if project else 'Project'}'.",
            ),
            user_id=member.invited_by_id,
        )

    return {"status": "ok", "message": "Invitation rejected"}


@router.post("/{project_id}/invite")
def invite_user_by_id(
    project_id: int,
    data: ProjectInviteCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> dict:
    """Invite a user to a project using their unique User ID."""
    from fastapi import HTTPException
    project = service.get_project(project_id)
    check_project_access_or_membership(project, current_user, session, "invite to")

    target_user = session.get(User, data.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID #{data.user_id} does not exist.",
        )

    # Check existing membership
    existing = session.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == data.user_id,
    ).first()

    if existing:
        if existing.status == "accepted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User #{data.user_id} is already an active member of this project.",
            )
        existing.status = "pending"
        existing.invited_by_id = current_user.id
        session.commit()
    else:
        new_member = ProjectMember(
            project_id=project_id,
            user_id=data.user_id,
            role="member",
            status="pending",
            invited_by_id=current_user.id,
        )
        session.add(new_member)
        session.commit()

    # Dispatch notification to target user
    from app.notifications.schemas import NotificationCreate
    from app.notifications.service import NotificationService
    NotificationService(session).create_notification(
        NotificationCreate(
            title="Project Invitation",
            message=f"{current_user.username} (ID: #{current_user.id}) invited you to collaborate on project '{project.name}'.",
        ),
        user_id=target_user.id,
    )

    return {
        "status": "ok",
        "message": f"Invitation sent to {target_user.username} (ID: #{target_user.id})",
    }


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_project_members(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectMemberRead]:
    """List members and collaborators of a project with online status."""
    project = service.get_project(project_id)
    check_project_access_or_membership(project, current_user, session, "view members of")

    # Project leader (creator) or admin can view members' token usage
    is_leader_or_admin = (current_user.role == "admin") or (project.user_id == current_user.id)

    members = session.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.status.in_(["accepted", "pending"]),
    ).all()

    result = []
    for m in members:
        u = session.get(User, m.user_id)
        if not u:
            continue
        result.append(
            ProjectMemberRead(
                id=m.id,
                project_id=project_id,
                user_id=u.id,
                username=u.username,
                role=m.role,
                status=m.status,
                is_online=u.is_online,
                token_usage=(u.token_usage or 0) if is_leader_or_admin else None,
                created_at=m.created_at,
            )
        )
    return result


@router.delete("/{project_id}/members/{user_id}")
def remove_project_member(
    project_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProjectService = Depends(get_project_service),
) -> dict:
    """Admin or project creator can remove a user from the project."""
    from fastapi import HTTPException
    from app.storage.models import Task

    project = service.get_project(project_id)

    # Only admin or project owner can remove members
    if current_user.role != "admin" and project.user_id != current_user.id and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or an admin can remove collaborators.",
        )

    member = session.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in project")

    # Unassign tasks assigned to this user in this project
    session.query(Task).filter(
        Task.project_id == project_id,
        Task.assigned_user_id == user_id,
    ).update({"assigned_user_id": None})

    session.delete(member)
    session.commit()

    # Send notification to removed user if someone else removed them
    if current_user.id != user_id:
        from app.notifications.schemas import NotificationCreate
        from app.notifications.service import NotificationService
        NotificationService(session).create_notification(
            NotificationCreate(
                title="Project Access Updated",
                message=f"You have been removed from project '{project.name}'.",
            ),
            user_id=user_id,
        )

    return {"status": "ok", "message": f"User #{user_id} removed from project"}


