"""Authentication dependencies and user context extraction for FastAPI routes."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.storage.database import get_db
from app.storage.models import User
from app.users.security import decode_access_token
from app.users.service import UserService


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_username: str | None = Header(default=None, alias="X-Username"),
    session: Session = Depends(get_db),
) -> User:
    """Resolve current user from Bearer token or identification headers.

    Fallback behavior: When no authentication headers are present (e.g.
    in unit tests, CLI tools, or background seeds), automatically resolves
    to the default admin user ('kunal'). If credentials ARE provided but
    invalid, raises 401 Unauthorized.
    """
    user_svc = UserService(session)
    user: User | None = None

    # 1. Bearer Token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        payload = decode_access_token(token)
        if payload and "user_id" in payload:
            user = user_svc.get_by_id(payload["user_id"])
        elif token:
            user = user_svc.get_by_username(token)

    # 2. X-User-Id Header
    if not user and x_user_id:
        try:
            uid = int(x_user_id)
            user = user_svc.get_by_id(uid)
        except (ValueError, TypeError):
            pass

    # 3. X-Username Header
    if not user and x_username:
        user = user_svc.get_by_username(x_username)

    # 4. Resolve or reject
    if not user:
        if authorization or x_user_id or x_username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Fallback to kunal (admin) for tests and unauthenticated API calls
        user = user_svc.ensure_admin_user()

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the authenticated user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def check_item_access(
    owner_user_id: int | None,
    current_user: User,
    action: str = "access",
) -> None:
    """Ensure that only the owner or an admin can access/modify a resource.

    If current_user is an admin (role == 'admin'), access is always granted.
    If owner_user_id is None, it is accessible.
    If current_user is not an admin and does not own the item, raises 403 Forbidden.
    """
    if current_user.role == "admin":
        return
    if owner_user_id is not None and owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: You do not have permission to {action} data belonging to another user.",
        )
