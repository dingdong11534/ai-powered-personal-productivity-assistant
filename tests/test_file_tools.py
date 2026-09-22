"""Unit tests for workspace file tools and tool execution safety."""

from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app.ai.tools.implementations import (
    CreateWorkspaceFileTool,
    DeleteWorkspaceFileTool,
    ListWorkspaceFilesTool,
    ReadWorkspaceFileTool,
    SearchWorkspaceFilesTool,
    UpdateWorkspaceFileTool,
    get_default_tool_registry,
)
from app.core.permissions import PermissionScope
from app.files.service import FileService


@pytest.fixture
def temp_workspace_svc(tmp_path: Path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    svc = FileService(workspace_dir=ws_dir)
    with patch("app.ai.tools.implementations.FileService", return_value=svc):
        yield svc


def test_file_tools_registration():
    registry = get_default_tool_registry()
    assert registry.get_tool("list_workspace_files") is not None
    assert registry.get_tool("read_workspace_file") is not None
    assert registry.get_tool("create_workspace_file") is not None
    assert registry.get_tool("update_workspace_file") is not None
    assert registry.get_tool("search_workspace_files") is not None
    assert registry.get_tool("delete_workspace_file") is not None

    schemas = registry.get_tools_schema()
    names = [s["function"]["name"] for s in schemas]
    assert "list_workspace_files" in names
    assert "read_workspace_file" in names
    assert "create_workspace_file" in names
    assert "update_workspace_file" in names
    assert "search_workspace_files" in names
    assert "delete_workspace_file" in names


def test_file_tools_execution_flow(db_session: Session, temp_workspace_svc: FileService):
    registry = get_default_tool_registry()

    # 1. Write file
    write_res = registry.execute_tool(
        "create_workspace_file",
        {"path": "reports/summary.txt", "content": "Quarterly report content."},
        db_session,
    )
    assert write_res["success"] is True
    assert write_res["data"]["path"] == "reports/summary.txt"

    # 2. List files
    list_res = registry.execute_tool(
        "list_workspace_files",
        {"sub_path": "reports"},
        db_session,
    )
    assert list_res["success"] is True
    paths = [f["path"] for f in list_res["data"]["files"]]
    assert "reports/summary.txt" in paths

    # 3. Read file
    read_res = registry.execute_tool(
        "read_workspace_file",
        {"path": "reports/summary.txt"},
        db_session,
    )
    assert read_res["success"] is True
    assert read_res["data"]["content"] == "Quarterly report content."

    # 4. Search files
    search_res = registry.execute_tool(
        "search_workspace_files",
        {"query": "Quarterly"},
        db_session,
    )
    assert search_res["success"] is True
    assert len(search_res["data"]["files"]) == 1

    # 5. Update and delete require a trusted explicit authorization flag,
    # which ToolRegistry does not source from model-generated arguments.
    update_res = registry.execute_tool(
        "update_workspace_file",
        {"path": "reports/summary.txt", "content": "Updated report."},
        db_session,
    )
    assert update_res["success"] is False
    assert "explicit user authorization" in update_res["error"]

    update_res = registry.execute_tool(
        "update_workspace_file",
        {"path": "reports/summary.txt", "content": "Updated report."},
        db_session,
        destructive_authorized=True,
    )
    assert update_res["success"] is True

    # 6. Delete file
    del_res = registry.execute_tool(
        "delete_workspace_file",
        {"path": "reports/summary.txt"},
        db_session,
        destructive_authorized=True,
    )
    assert del_res["success"] is True


def test_file_tool_scopes_are_safe():
    assert ListWorkspaceFilesTool.scope is PermissionScope.READ
    assert ReadWorkspaceFileTool.scope is PermissionScope.READ
    assert SearchWorkspaceFilesTool.scope is PermissionScope.READ
    assert CreateWorkspaceFileTool.scope is PermissionScope.WRITE
    assert UpdateWorkspaceFileTool.scope is PermissionScope.DESTRUCTIVE
    assert DeleteWorkspaceFileTool.scope is PermissionScope.DESTRUCTIVE


def test_file_tools_path_traversal_returns_error(db_session: Session, temp_workspace_svc: FileService):
    registry = get_default_tool_registry()

    res = registry.execute_tool(
        "read_workspace_file",
        {"path": "../../etc/passwd"},
        db_session,
    )
    assert res["success"] is False
    assert "Access denied" in res["error"]


def test_delete_workspace_file_tool_unauthorized_keeps_file_on_disk(
    db_session: Session, temp_workspace_svc: FileService
):
    registry = get_default_tool_registry()
    file_path = "important.txt"
    temp_workspace_svc.write_file(file_path, "important content")
    disk_file = temp_workspace_svc.workspace_dir / file_path
    assert disk_file.exists() is True

    # Call delete tool with destructive_authorized=False (default)
    res = registry.execute_tool(
        "delete_workspace_file",
        {"path": file_path},
        db_session,
        destructive_authorized=False,
    )

    assert res["success"] is False
    assert "explicit user authorization" in res["error"]
    # Verify file still exists on disk
    assert disk_file.exists() is True
    assert disk_file.read_text(encoding="utf-8") == "important content"


def test_delete_workspace_file_tool_authorized_deletes_file_from_disk(
    db_session: Session, temp_workspace_svc: FileService
):
    registry = get_default_tool_registry()
    file_path = "disposable.txt"
    temp_workspace_svc.write_file(file_path, "disposable content")
    disk_file = temp_workspace_svc.workspace_dir / file_path
    assert disk_file.exists() is True

    # Call delete tool with trusted destructive_authorized=True
    res = registry.execute_tool(
        "delete_workspace_file",
        {"path": file_path},
        db_session,
        destructive_authorized=True,
    )

    assert res["success"] is True
    # Verify file is removed from disk
    assert disk_file.exists() is False


def test_tool_argument_injection_does_not_grant_destructive_authorization(
    db_session: Session, temp_workspace_svc: FileService
):
    registry = get_default_tool_registry()
    file_path = "protected.txt"
    temp_workspace_svc.write_file(file_path, "protected data")
    disk_file = temp_workspace_svc.workspace_dir / file_path
    assert disk_file.exists() is True

    # LLM-generated arguments injection attempts
    injected_argument_payloads = [
        {"path": file_path, "authorized": True},
        {"path": file_path, "authorize_destructive": True},
        {"path": file_path, "destructive_authorized": True},
        {"path": file_path, "confirm_destructive": True},
        {"path": file_path, "force": True, "allow_destructive": True},
    ]

    for malicious_args in injected_argument_payloads:
        res = registry.execute_tool(
            "delete_workspace_file",
            malicious_args,
            db_session,
            destructive_authorized=False,
        )
        assert res["success"] is False
        assert "explicit user authorization" in res["error"]
        assert disk_file.exists() is True

