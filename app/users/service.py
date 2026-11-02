"""UserService managing authentication, user registration, and admin provisioning."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import User
from app.users.repository import UserRepository
from app.users.security import create_access_token, hash_password, verify_password


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = UserRepository(db)

    def ensure_admin_user(self) -> User:
        """Ensure default admin user 'kunal' exists with password 'kunalreward34'."""
        admin = self.repo.get_by_username("kunal")
        if not admin:
            admin = User(
                username="kunal",
                password_hash=hash_password("kunalreward34"),
                role="admin",
            )
            admin = self.repo.create(admin)
        elif admin.role != "admin":
            admin = self.repo.update(admin, {"role": "admin"})
        return admin

    def register_user(self, username: str, password: str, role: str = "user") -> tuple[User, str]:
        clean_username = username.strip().lower()
        if not clean_username:
            raise ValueError("Username cannot be empty")
        if len(clean_username) < 2:
            raise ValueError("Username must be at least 2 characters")
        if not password or len(password) < 1:
            raise ValueError("Password cannot be empty")

        existing = self.repo.get_by_username(clean_username)
        if existing:
            raise ValueError(f"User '{clean_username}' already exists")

        # Kunal is always admin
        assigned_role = "admin" if clean_username == "kunal" else role

        user = User(
            username=clean_username,
            password_hash=hash_password(password),
            role=assigned_role,
        )
        saved_user = self.repo.create(user)
        token = create_access_token(saved_user.id, saved_user.username, saved_user.role)
        return saved_user, token

    def authenticate_user(self, username: str, password: str) -> tuple[User, str]:
        clean_username = username.strip().lower()
        user = self.repo.get_by_username(clean_username)
        if not user:
            # Special bootstrap: If kunal doesn't exist yet and logs in with default password
            if clean_username == "kunal" and password == "kunalreward34":
                user = self.ensure_admin_user()
            else:
                raise ValueError("Invalid username or password")

        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid username or password")

        token = create_access_token(user.id, user.username, user.role)
        return user, token

    def get_by_id(self, user_id: int) -> User | None:
        return self.repo.get_by_id(user_id)

    def get_by_username(self, username: str) -> User | None:
        return self.repo.get_by_username(username)

    def list_users(self) -> list[User]:
        return self.repo.list()

    def get_custom_api_keys(self, user_id: int) -> dict[str, str]:
        user = self.get_by_id(user_id)
        if not user or not user.custom_api_keys:
            return {}
        try:
            import json
            data = json.loads(user.custom_api_keys)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def update_custom_api_key(self, user_id: int, provider: str, key: str | None) -> dict[str, str]:
        import json
        user = self.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        keys = self.get_custom_api_keys(user_id)
        provider_clean = provider.strip().lower()
        if key is not None and key.strip():
            keys[provider_clean] = key.strip()
        else:
            keys.pop(provider_clean, None)
        self.repo.update(user, {"custom_api_keys": json.dumps(keys) if keys else None})
        return keys

