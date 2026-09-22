"""Unit and security tests for FileService and path traversal defense."""

from pathlib import Path
import pytest

from app.files.exceptions import (
    FileAccessDeniedError,
    FileNotFoundInWorkspaceError,
    FileOperationError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.files.service import FileService


@pytest.fixture
def temp_workspace(tmp_path: Path) -> FileService:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    return FileService(workspace_dir=workspace_dir)


def test_path_traversal_attempts_raise_access_denied(temp_workspace: FileService):
    traversal_paths = [
        "../outside.txt",
        "../../etc/passwd",
        "/etc/passwd",
        "folder/../../outside.txt",
        "sub/../../../etc/shadow",
        "note\0file.txt",
    ]

    for bad_path in traversal_paths:
        with pytest.raises(FileAccessDeniedError):
            temp_workspace.resolve_and_validate_path(bad_path)


def test_write_and_read_file_in_workspace(temp_workspace: FileService):
    rel_path = "docs/notes.txt"
    content = "Sample content for assistant workspace."

    write_res = temp_workspace.write_file(rel_path, content)
    assert write_res.path == "docs/notes.txt"
    assert write_res.created is True
    assert write_res.bytes_written > 0

    read_res = temp_workspace.read_file(rel_path)
    assert read_res.path == "docs/notes.txt"
    assert read_res.content == content


def test_write_without_overwrite_raises_error(temp_workspace: FileService):
    rel_path = "config.txt"
    temp_workspace.write_file(rel_path, "Initial content")

    with pytest.raises(FileOperationError):
        temp_workspace.write_file(rel_path, "New content", overwrite=False)


def test_list_files_and_search(temp_workspace: FileService):
    temp_workspace.write_file("alpha.txt", "Alpha test content")
    temp_workspace.write_file("sub/beta.txt", "Beta test content")
    temp_workspace.write_file("sub/gamma.md", "Markdown notes")

    files = temp_workspace.list_files()
    paths = [f.path for f in files]
    assert "alpha.txt" in paths
    assert "sub" in paths
    assert "sub/beta.txt" in paths
    assert "sub/gamma.md" in paths

    search_res = temp_workspace.search_files("Beta")
    assert len(search_res) == 1
    assert search_res[0].path == "sub/beta.txt"


def test_delete_file_and_directory(temp_workspace: FileService):
    temp_workspace.write_file("temp.txt", "Temporary file")
    temp_workspace.write_file("folder/sub.txt", "Sub file")

    assert temp_workspace.delete_file("temp.txt") is True
    with pytest.raises(FileNotFoundInWorkspaceError):
        temp_workspace.read_file("temp.txt")

    assert temp_workspace.delete_file("folder") is True
    with pytest.raises(FileNotFoundInWorkspaceError):
        temp_workspace.list_files("folder")


def test_cannot_delete_or_write_root(temp_workspace: FileService):
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.delete_file("")

    with pytest.raises(FileAccessDeniedError):
        temp_workspace.write_file("", "invalid")


def test_read_missing_file_raises_not_found(temp_workspace: FileService):
    with pytest.raises(FileNotFoundInWorkspaceError):
        temp_workspace.read_file("nonexistent.txt")


def test_windows_paths_and_repeated_separators_are_safe(temp_workspace: FileService):
    for path in (r"C:\\Windows\\system.ini", r"\\\\server\\share\\file.txt", r"..\\outside.txt"):
        with pytest.raises(FileAccessDeniedError):
            temp_workspace.resolve_and_validate_path(path)

    temp_workspace.write_file("nested//note.txt", "safe")
    assert temp_workspace.read_file("nested///note.txt").content == "safe"


def test_symlink_escape_is_rejected(temp_workspace: FileService, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = temp_workspace.workspace_dir / "escape.txt"
    link.symlink_to(outside)
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.read_file("escape.txt")


def test_binary_and_size_limits_are_rejected(temp_workspace: FileService):
    binary = temp_workspace.workspace_dir / "binary.bin"
    binary.write_bytes(b"\x00binary")
    with pytest.raises(UnsupportedFileTypeError):
        temp_workspace.read_file("binary.bin")

    temp_workspace.max_write_bytes = 3
    with pytest.raises(FileTooLargeError):
        temp_workspace.write_file("large.txt", "four")


def test_backslash_traversal_literal_rejected(temp_workspace: FileService):
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.resolve_and_validate_path(r"..\..\secret")


def test_symlink_escape_operations_individually_rejected(temp_workspace: FileService, tmp_path: Path):
    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("confidential data")
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "nested_outside.txt").write_text("nested outside data")

    file_link = temp_workspace.workspace_dir / "symlink_file.txt"
    file_link.symlink_to(outside_file)

    dir_link = temp_workspace.workspace_dir / "symlink_dir"
    dir_link.symlink_to(outside_dir)

    # 1. Read
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.read_file("symlink_file.txt")

    # 2. Write
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.write_file("symlink_file.txt", "overwrite attempt")

    # 3. Delete
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.delete_file("symlink_file.txt")

    # 4. List
    with pytest.raises(FileAccessDeniedError):
        temp_workspace.list_files("symlink_dir")
    listed_paths = [f.path for f in temp_workspace.list_files()]
    assert "nested_outside.txt" not in listed_paths

    # 5. Search
    search_results = temp_workspace.search_files("confidential")
    assert len(search_results) == 0


def test_read_size_limit_raises_file_too_large(temp_workspace: FileService):
    large_file = temp_workspace.workspace_dir / "oversized.txt"
    large_file.write_text("A" * (temp_workspace.max_read_bytes + 10))
    with pytest.raises(FileTooLargeError):
        temp_workspace.read_file("oversized.txt")


def test_scan_result_limit_and_depth_enforcement(temp_workspace: FileService):
    # Result capping
    temp_workspace.max_results = 3
    for i in range(6):
        temp_workspace.write_file(f"cap_test_{i}.txt", f"match content {i}")

    listed = temp_workspace.list_files()
    assert len(listed) == 3

    searched = temp_workspace.search_files("match")
    assert len(searched) == 3

    # Depth limit enforcement
    temp_workspace.max_depth = 3
    deep_path = "l1/l2/l3/l4/file.txt"
    with pytest.raises(FileAccessDeniedError) as exc_info:
        temp_workspace.resolve_and_validate_path(deep_path)
    assert "maximum depth" in str(exc_info.value)

