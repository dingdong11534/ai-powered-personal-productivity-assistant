"""Integration tests for the /files REST API endpoints."""

from pathlib import Path
from unittest.mock import patch
import pytest

from app.files.service import FileService


@pytest.fixture
def api_workspace_svc(tmp_path: Path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    svc = FileService(workspace_dir=ws_dir)
    with patch("app.interfaces.api.files.get_file_service", return_value=svc):
        yield svc


def test_write_and_read_file_via_api(client, api_workspace_svc: FileService):

    # Write file
    resp = client.post(
        "/files/write",
        json={"path": "notes/todo.txt", "content": "Buy groceries and finish Phase 6."},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["path"] == "notes/todo.txt"
    assert data["created"] is True

    # Read file
    resp = client.get("/files/read", params={"path": "notes/todo.txt"})
    assert resp.status_code == 200
    read_data = resp.json()
    assert read_data["content"] == "Buy groceries and finish Phase 6."


def test_list_and_search_files_via_api(client, api_workspace_svc: FileService):
    api_workspace_svc.write_file("doc1.txt", "Alpha documentation")
    api_workspace_svc.write_file("doc2.md", "Beta documentation")

    # List all
    resp = client.get("/files")
    assert resp.status_code == 200
    files = resp.json()
    assert len(files) == 2

    # Search query
    resp = client.get("/files", params={"search": "Beta"})
    assert resp.status_code == 200
    search_files = resp.json()
    assert len(search_files) == 1
    assert search_files[0]["path"] == "doc2.md"


def test_delete_file_via_api(client, api_workspace_svc: FileService):
    api_workspace_svc.write_file("temp.log", "Log data")

    rejected = client.delete("/files", params={"path": "temp.log"})
    assert rejected.status_code == 403

    resp = client.delete("/files", params={"path": "temp.log", "confirm_destructive": True})
    assert resp.status_code == 200

    resp = client.get("/files/read", params={"path": "temp.log"})
    assert resp.status_code == 404


def test_delete_file_api_unauthorized_preserves_disk_file(client, api_workspace_svc: FileService):
    api_workspace_svc.write_file("keep_me.txt", "keep this data")
    disk_file = api_workspace_svc.workspace_dir / "keep_me.txt"
    assert disk_file.exists() is True

    resp = client.delete("/files", params={"path": "keep_me.txt"})
    assert resp.status_code == 403
    # Confirm file still exists on disk
    assert disk_file.exists() is True
    assert disk_file.read_text(encoding="utf-8") == "keep this data"


def test_delete_file_api_authorized_removes_disk_file(client, api_workspace_svc: FileService):
    api_workspace_svc.write_file("delete_me.txt", "delete this data")
    disk_file = api_workspace_svc.workspace_dir / "delete_me.txt"
    assert disk_file.exists() is True

    resp = client.delete("/files", params={"path": "delete_me.txt", "confirm_destructive": True})
    assert resp.status_code == 200
    # Confirm file is deleted from disk
    assert disk_file.exists() is False


def test_path_traversal_api_returns_403(client, api_workspace_svc: FileService):

    resp = client.get("/files/read", params={"path": "../../etc/passwd"})
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]

