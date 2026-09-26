"""Tests for app.core.permissions.

Run with: pytest tests/test_permissions.py -v
"""

import pytest

from app.core.permissions import (
    PermissionChecker,
    PermissionDenied,
    PermissionRequest,
    PermissionScope,
)


def test_read_is_allowed():
    checker = PermissionChecker()
    request = PermissionRequest(
        scope=PermissionScope.READ, actor="ai", description="list tasks"
    )
    checker.check(request)  # should not raise


def test_write_is_allowed():
    checker = PermissionChecker()
    request = PermissionRequest(
        scope=PermissionScope.WRITE, actor="ai", description="create task"
    )
    checker.check(request)  # should not raise


def test_destructive_is_denied():
    checker = PermissionChecker()
    request = PermissionRequest(
        scope=PermissionScope.DESTRUCTIVE, actor="ai", description="delete task"
    )
    with pytest.raises(PermissionDenied):
        checker.check(request)


def test_external_is_allowed():
    """Phase 7: EXTERNAL scope is now allowed by PermissionChecker.
    Security is enforced at the HTTP client layer (domain allowlist + SSRF guard),
    not at the permission gate.
    """
    checker = PermissionChecker()
    request = PermissionRequest(
        scope=PermissionScope.EXTERNAL, actor="ai", description="call weather API"
    )
    checker.check(request)  # must not raise
