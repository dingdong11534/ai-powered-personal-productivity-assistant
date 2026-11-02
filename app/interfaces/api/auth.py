"""FastAPI routes for user authentication, registration, and user profiles."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.storage.database import get_db
from app.storage.models import Project, User
from app.users.schemas import AuthResponse, UserCreate, UserLogin, UserProfilePublic, UserRead
from app.users.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, session: Session = Depends(get_db)) -> AuthResponse:
    """Create a new user account and return an authentication token."""
    svc = UserService(session)
    try:
        user, token = svc.register_user(data.username, data.password)
        user.last_active_at = datetime.utcnow()
        session.commit()
        return AuthResponse(
            user=UserRead(
                id=user.id,
                username=user.username,
                role=user.role,
                is_online=True,
                token_usage=user.token_usage or 0,
                created_at=user.created_at.isoformat() if user.created_at else None,
            ),
            token=token,
            access_token=token,
            message=f"Welcome {user.username}! Account created.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/login", response_model=AuthResponse)
def login(data: UserLogin, session: Session = Depends(get_db)) -> AuthResponse:
    """Authenticate with username and password, returning user data and token."""
    svc = UserService(session)
    try:
        user, token = svc.authenticate_user(data.username, data.password)
        user.last_active_at = datetime.utcnow()
        session.commit()
        return AuthResponse(
            user=UserRead(
                id=user.id,
                username=user.username,
                role=user.role,
                is_online=True,
                token_usage=user.token_usage or 0,
                created_at=user.created_at.isoformat() if user.created_at else None,
            ),
            token=token,
            access_token=token,
            message=f"Logged in as {user.username}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))


@router.get("/me", response_model=UserRead)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UserRead:
    """Return the profile of the currently authenticated user."""
    current_user.last_active_at = datetime.utcnow()
    session.commit()
    return UserRead(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        is_online=True,
        token_usage=current_user.token_usage or 0,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


@router.post("/heartbeat")
def heartbeat(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Update active heartbeat for current user."""
    current_user.last_active_at = datetime.utcnow()
    session.commit()
    return {
        "status": "ok",
        "user_id": current_user.id,
        "is_online": True,
        "token_usage": current_user.token_usage or 0,
    }


@router.post("/offline")
def set_offline(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """Explicitly mark user offline when closing tab, navigating away, or hidden."""
    current_user.last_active_at = None
    session.commit()
    return {
        "status": "ok",
        "user_id": current_user.id,
        "is_online": False,
    }


@router.get("/users", response_model=list[UserProfilePublic])
def list_registered_users(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserProfilePublic]:
    """List all registered users with their unique ID, online status, and token usage if admin or project leader."""
    svc = UserService(session)
    users = svc.list_users()

    # Admin and project leaders can see all tokens used by users
    is_admin = current_user.role == "admin"
    is_project_leader = session.query(Project).filter(Project.user_id == current_user.id).first() is not None
    can_see_tokens = is_admin or is_project_leader

    return [
        UserProfilePublic(
            id=u.id,
            username=u.username,
            role=u.role,
            is_online=u.is_online,
            token_usage=(u.token_usage or 0) if (can_see_tokens or u.id == current_user.id) else None,
        )
        for u in users
    ]


@router.get("/users/{user_id}/profile", response_model=UserProfilePublic)
def get_user_public_profile(
    user_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfilePublic:
    """View a user's public profile (unique ID and online status; token usage visible if admin or project leader)."""
    svc = UserService(session)
    u = svc.get_by_id(user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User #{user_id} not found")

    is_admin = current_user.role == "admin"
    is_project_leader = session.query(Project).filter(Project.user_id == current_user.id).first() is not None
    can_see_tokens = is_admin or is_project_leader or (current_user.id == u.id)

    return UserProfilePublic(
        id=u.id,
        username=u.username,
        role=u.role,
        is_online=u.is_online,
        token_usage=(u.token_usage or 0) if can_see_tokens else None,
    )

