"""End-to-End integration test for AI assistant file operations."""

from pathlib import Path
from unittest.mock import patch
import pytest

from app.files.service import FileService


@pytest.fixture
def mock_ai_workspace(tmp_path: Path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    svc = FileService(workspace_dir=ws_dir)
    with patch("app.ai.tools.implementations.FileService", return_value=svc), \
         patch("app.interfaces.api.files.get_file_service", return_value=svc):
        yield svc


def test_ai_file_creation_loop(client, mock_ai_workspace: FileService):
    conv_response = client.post("/conversations", json={"title": "File AI Integration Test"})
    assert conv_response.status_code == 201
    conversation_id = conv_response.json()["id"]

    # 1. Ask AI to create/write file
    resp = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Please write file notes.txt with assistant data"},
    )
    assert resp.status_code == 201

    # Verify file was written inside workspace
    assert mock_ai_workspace.read_file("notes.txt").content == "Assistant workspace note content"

    # 2. Ask AI to list files
    resp = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Can you list workspace files?"},
    )
    assert resp.status_code == 201

    # 3. Ask AI to read file
    resp = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Please read file notes.txt"},
    )
    assert resp.status_code == 201

    # 4. Ask AI to delete file
    resp = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Please delete file notes.txt", "authorize_destructive": True},
    )
    assert resp.status_code == 201

    # Verify file was deleted
    assert not (mock_ai_workspace.workspace_dir / "notes.txt").exists()
