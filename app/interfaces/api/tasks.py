"""
Task API routes.

Deliberately thin: each function parses input (via the type-hinted
Pydantic schema or query parameters, which FastAPI validates
automatically before the function body even runs), calls exactly one
service method, and returns the result. No SQLAlchemy, no session
handling, no business rules here — see app.tasks.service,
app.tasks.tag_service, and app.tasks.dependency_service for those.

Route paths use "" rather than "/" for the collection endpoints, same
reasoning as app.interfaces.api.projects.

Tag and dependency routes are nested under `/tasks/{task_id}/...` since
they act on a specific task's associations; tag *creation* itself
(`POST /tags`, `GET /tags`) lives in app.interfaces.api.tags instead,
since creating a tag isn't an action on any particular task.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import check_item_access, get_current_user
from app.notifications.schemas import NotificationCreate
from app.notifications.service import NotificationService, record_activity
from app.storage.database import get_db
from app.storage.models import Project, ProjectMember, Task, TaskRequest, TaskStatus, User
from app.tasks.dependency_service import TaskDependencyService
from app.tasks.schemas import (
    TagRead,
    TaskAssignmentRequestCreate,
    TaskAssignmentRequestRead,
    TaskCreate,
    TaskDependencyCreate,
    TaskRead,
    TaskUpdate,
)
from app.tasks.service import TaskService
from app.tasks.tag_service import TagService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def check_task_access(
    task: Task,
    current_user: User,
    session: Session,
    action: str = "access",
) -> None:
    if current_user.role == "admin":
        return
    if task.user_id == current_user.id or task.assigned_user_id == current_user.id:
        return
    if task.project_id:
        is_member = session.query(ProjectMember).filter(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == current_user.id,
            ProjectMember.status == "accepted",
        ).first()
        if is_member:
            return
    from fastapi import HTTPException
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access denied: You cannot {action} this task.",
    )



def get_task_service(db: Session = Depends(get_db)) -> TaskService:

    return TaskService(db)


def get_tag_service(db: Session = Depends(get_db)) -> TagService:
    return TagService(db)


def get_dependency_service(db: Session = Depends(get_db)) -> TaskDependencyService:
    return TaskDependencyService(db)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
    db: Session = Depends(get_db),
) -> TaskRead:
    task = service.create_task(data, user_id=current_user.id)
    record_activity(db, f"Task created: {task.title}", body=task.description, source="task", user_id=current_user.id)
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    status_: TaskStatus | None = Query(default=None, alias="status"),
    priority: int | None = Query(default=None, ge=1, le=4),
    project_id: int | None = Query(default=None),
    tag_id: int | None = Query(default=None),
    deadline_before: datetime | None = Query(default=None),
    deadline_after: datetime | None = Query(default=None),
    completed: bool | None = Query(default=None),
    search: str | None = Query(default=None, description="Substring match on title/description."),
    all_users: bool = Query(default=False, description="Admin only: list tasks across all users."),
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
) -> list[TaskRead]:
    target_user_id = None if (all_users and current_user.role == "admin") else current_user.id
    return service.list_tasks(
        skip=skip,
        limit=limit,
        status=status_,
        priority=priority,
        project_id=project_id,
        tag_id=tag_id,
        deadline_before=deadline_before,
        deadline_after=deadline_after,
        completed=completed,
        search=search,
        user_id=target_user_id,
    )



@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
    db: Session = Depends(get_db),
) -> TaskRead:
    task = service.get_task(task_id)
    check_task_access(task, current_user, db, "view")
    return task


@router.put("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
    db: Session = Depends(get_db),
) -> TaskRead:
    existing = service.get_task(task_id)
    check_task_access(existing, current_user, db, "modify")
    task = service.update_task(task_id, data)
    status_msg = f" (Status: {task.status})" if data.status else ""
    record_activity(db, f"Task updated: {task.title}{status_msg}", source="task", user_id=current_user.id)
    return task



@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    service: TaskService = Depends(get_task_service),
    db: Session = Depends(get_db),
) -> Response:
    existing = service.get_task(task_id)
    check_item_access(existing.user_id, current_user, "delete")
    service.delete_task(task_id)
    record_activity(db, f"Task deleted: ID #{task_id}", source="task", user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Tags on a task ---


@router.get("/{task_id}/tags", response_model=list[TagRead])
def list_task_tags(
    task_id: int,
    current_user: User = Depends(get_current_user),
    service: TagService = Depends(get_tag_service),
    tasks: TaskService = Depends(get_task_service),
) -> list[TagRead]:
    task = tasks.get_task(task_id)
    check_item_access(task.user_id, current_user, "view")
    return service.get_task_tags(task_id)


@router.post("/{task_id}/tags/{tag_id}", response_model=TaskRead)
def attach_tag(
    task_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    service: TagService = Depends(get_tag_service),
    tasks: TaskService = Depends(get_task_service),
) -> TaskRead:
    task = tasks.get_task(task_id)
    check_item_access(task.user_id, current_user, "modify")
    return service.attach_tag_to_task(task_id, tag_id)


@router.delete("/{task_id}/tags/{tag_id}", response_model=TaskRead)
def detach_tag(
    task_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    service: TagService = Depends(get_tag_service),
    tasks: TaskService = Depends(get_task_service),
) -> TaskRead:
    task = tasks.get_task(task_id)
    check_item_access(task.user_id, current_user, "modify")
    return service.detach_tag_from_task(task_id, tag_id)


# --- Dependencies on a task ---


@router.get("/{task_id}/dependencies", response_model=list[int])
def list_task_dependencies(
    task_id: int,
    current_user: User = Depends(get_current_user),
    tasks: TaskService = Depends(get_task_service),
    service: TaskDependencyService = Depends(get_dependency_service),
) -> list[int]:
    task = tasks.get_task(task_id)
    check_item_access(task.user_id, current_user, "view")
    return service.list_dependencies(task_id)


@router.post(
    "/{task_id}/dependencies",
    status_code=status.HTTP_201_CREATED,
)
def add_task_dependency(
    task_id: int,
    data: TaskDependencyCreate,
    current_user: User = Depends(get_current_user),
    tasks: TaskService = Depends(get_task_service),
    service: TaskDependencyService = Depends(get_dependency_service),
) -> dict[str, int]:
    task = tasks.get_task(task_id)
    check_item_access(task.user_id, current_user, "modify")
    dep_task = tasks.get_task(data.depends_on_task_id)
    check_item_access(dep_task.user_id, current_user, "modify")
    dependency = service.add_dependency(task_id, data.depends_on_task_id)
    return {"task_id": dependency.task_id, "depends_on_task_id": dependency.depends_on_task_id}


@router.delete(
    "/{task_id}/dependencies/{depends_on_task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_task_dependency(
    task_id: int,
    depends_on_task_id: int,
    current_user: User = Depends(get_current_user),
    tasks: TaskService = Depends(get_task_service),
    service: TaskDependencyService = Depends(get_dependency_service),
) -> Response:
    task = tasks.get_task(task_id)
    check_item_access(task.user_id, current_user, "modify")
    service.remove_dependency(task_id, depends_on_task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------
# Task Assignment Requests & Collaboration
# -------------------------------------------------------------

@router.get("/requests/pending", response_model=list[TaskAssignmentRequestRead])
def list_pending_task_requests(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[TaskAssignmentRequestRead]:
    """List incoming pending task assignment requests for the current user."""
    reqs = session.query(TaskRequest).filter(
        TaskRequest.to_user_id == current_user.id,
        TaskRequest.status == "pending",
    ).all()
    results = []
    for r in reqs:
        task = session.get(Task, r.task_id)
        if not task:
            continue
        from_u = session.get(User, r.from_user_id)
        to_u = session.get(User, r.to_user_id)
        proj = session.get(Project, r.project_id) if r.project_id else None
        results.append(
            TaskAssignmentRequestRead(
                id=r.id,
                task_id=task.id,
                task_title=task.title,
                task_priority=task.priority,
                task_deadline=task.deadline,
                project_id=proj.id if proj else None,
                project_name=proj.name if proj else None,
                from_user_id=r.from_user_id,
                from_username=from_u.username if from_u else "User",
                to_user_id=r.to_user_id,
                to_username=to_u.username if to_u else "User",
                notes=r.notes,
                status=r.status,
                created_at=r.created_at,
            )
        )
    return results


@router.post("/{task_id}/request-assign")
def request_task_assignment(
    task_id: int,
    data: TaskAssignmentRequestCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: TaskService = Depends(get_task_service),
) -> dict:
    """Request a task to be assigned to another user by their unique User ID, with optional notes."""
    from fastapi import HTTPException
    task = service.get_task(task_id)
    check_task_access(task, current_user, session, "assign")

    target_user = session.get(User, data.to_user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User #{data.to_user_id} not found",
        )

    req = TaskRequest(
        task_id=task.id,
        from_user_id=current_user.id,
        to_user_id=target_user.id,
        project_id=task.project_id,
        notes=data.notes,
        status="pending",
    )
    session.add(req)
    session.commit()

    NotificationService(session).create_notification(
        NotificationCreate(
            title="Task Assignment Request",
            message=f"{current_user.username} (ID: #{current_user.id}) requested to assign task '{task.title}' to you. Notes: {data.notes or 'None'}",
        ),
        user_id=target_user.id,
    )

    return {
        "status": "ok",
        "message": f"Task request sent to {target_user.username} (ID: #{target_user.id})",
        "request_id": req.id,
    }


@router.post("/requests/{request_id}/accept")
def accept_task_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Target user accepts task request. The task is now officially assigned to them."""
    from fastapi import HTTPException
    req = session.get(TaskRequest, request_id)
    if not req or req.to_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task request not found")

    req.status = "accepted"
    task = session.get(Task, req.task_id)
    if task:
        task.assigned_user_id = current_user.id

    session.commit()

    if req.from_user_id != current_user.id:
        NotificationService(session).create_notification(
            NotificationCreate(
                title="Task Request Accepted",
                message=f"{current_user.username} (ID: #{current_user.id}) accepted the assignment for task '{task.title if task else 'Task'}'.",
            ),
            user_id=req.from_user_id,
        )

    return {"status": "ok", "message": "Task accepted and assigned to you"}


@router.post("/requests/{request_id}/reject")
def reject_task_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Target user rejects task request. The task is NOT assigned to them."""
    from fastapi import HTTPException
    req = session.get(TaskRequest, request_id)
    if not req or req.to_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task request not found")

    req.status = "rejected"
    task = session.get(Task, req.task_id)
    if task and task.assigned_user_id == current_user.id:
        task.assigned_user_id = None

    session.commit()

    if req.from_user_id != current_user.id:
        NotificationService(session).create_notification(
            NotificationCreate(
                title="Task Request Rejected",
                message=f"{current_user.username} (ID: #{current_user.id}) declined the task '{task.title if task else 'Task'}'.",
            ),
            user_id=req.from_user_id,
        )

    return {"status": "ok", "message": "Task request declined"}


