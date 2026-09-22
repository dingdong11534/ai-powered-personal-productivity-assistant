"""File Service implementing sandboxed workspace operations and path security enforcement."""

from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import shutil
from typing import Literal

from app.core.config import get_settings
from app.core.events import EventBus, file_events
from app.files.exceptions import (
    FileAccessDeniedError,
    FileNotFoundInWorkspaceError,
    FileOperationError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.files.schemas import FileInfo, FileReadResult, FileWriteResult


class FileService:
    """Service providing safe, sandboxed file operations inside workspace_dir."""

    def __init__(self, workspace_dir: Path | None = None, event_bus: EventBus | None = None):
        settings = get_settings()
        if workspace_dir is None:
            workspace_dir = settings.ensure_workspace_dir()
        self.workspace_dir = workspace_dir.resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.max_read_bytes = settings.max_file_read_bytes
        self.max_write_bytes = settings.max_file_write_bytes
        self.max_results = settings.max_file_results
        self.max_scan_entries = settings.max_file_scan_entries
        self.max_depth = settings.max_workspace_depth
        self.event_bus = event_bus or file_events

    def resolve_and_validate_path(self, relative_path: str) -> Path:
        """Resolve a relative path against workspace_dir and verify it stays within bounds.

        Raises FileAccessDeniedError if the path attempts to break out of the sandbox.
        """
        if not relative_path:
            return self.workspace_dir

        # Guard against null byte injection
        if "\0" in relative_path:
            raise FileAccessDeniedError("Null byte detected in path.")

        normalized_path = relative_path.replace("\\", "/")
        windows_path = PureWindowsPath(relative_path)
        p = Path(normalized_path)
        if p.is_absolute() or windows_path.is_absolute() or windows_path.drive:
            raise FileAccessDeniedError(f"Access denied: absolute path '{relative_path}' is not allowed.")

        if len(p.parts) > self.max_depth:
            raise FileAccessDeniedError("Access denied: workspace path exceeds the maximum depth.")

        target_path = (self.workspace_dir / p).resolve()

        # Check if resolved path is inside resolved workspace_dir
        try:
            target_path.relative_to(self.workspace_dir)
        except ValueError:
            raise FileAccessDeniedError(
                f"Access denied: path '{relative_path}' resolves outside the sandboxed workspace."
            )


        return target_path

    def _get_relative_str(self, path: Path) -> str:
        """Return path relative to workspace_dir as string."""
        rel = path.resolve().relative_to(self.workspace_dir)
        return str(rel) if str(rel) != "." else ""

    def list_files(self, sub_path: str = "") -> list[FileInfo]:
        """List files and subdirectories within sub_path in workspace."""
        base_dir = self.resolve_and_validate_path(sub_path)

        if not base_dir.exists():
            raise FileNotFoundInWorkspaceError(f"Path '{sub_path}' does not exist in workspace.")

        if base_dir.is_file():
            stat = base_dir.stat()
            return [
                FileInfo(
                    path=self._get_relative_str(base_dir),
                    size=stat.st_size,
                    is_directory=False,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            ]

        items: list[FileInfo] = []
        scanned = 0
        for p in sorted(base_dir.rglob("*")):
            scanned += 1
            if scanned > self.max_scan_entries or len(items) >= self.max_results:
                break
            # Ensure each child also stays inside sandbox
            try:
                p.resolve().relative_to(self.workspace_dir)
            except ValueError:
                continue

            if p.is_symlink() and not p.resolve().is_file():
                continue
            stat = p.stat()
            items.append(
                FileInfo(
                    path=self._get_relative_str(p),
                    size=0 if p.is_dir() else stat.st_size,
                    is_directory=p.is_dir(),
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )

        return items

    def read_file(self, relative_path: str) -> FileReadResult:
        """Read text content of a file in the workspace."""
        target_path = self.resolve_and_validate_path(relative_path)

        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundInWorkspaceError(
                f"File '{relative_path}' not found in workspace."
            )

        try:
            size = target_path.stat().st_size
            if size > self.max_read_bytes:
                raise FileTooLargeError(
                    f"File '{relative_path}' exceeds the {self.max_read_bytes}-byte read limit."
                )
            raw_content = target_path.read_bytes()
            if b"\0" in raw_content:
                raise UnsupportedFileTypeError(f"File '{relative_path}' is binary and cannot be read as text.")
            try:
                content = raw_content.decode("utf-8")
            except UnicodeDecodeError as err:
                raise UnsupportedFileTypeError(
                    f"File '{relative_path}' is not UTF-8 text and cannot be read."
                ) from err
            return FileReadResult(
                path=self._get_relative_str(target_path),
                content=content,
                size=size,
            )
        except (FileOperationError, FileTooLargeError, UnsupportedFileTypeError):
            raise
        except OSError as err:
            raise FileOperationError(f"Failed to read file '{relative_path}': {err}")

    def write_file(
        self,
        relative_path: str,
        content: str,
        overwrite: bool = True,
    ) -> FileWriteResult:
        """Write content into a file in the workspace, creating parent directories if needed."""
        target_path = self.resolve_and_validate_path(relative_path)

        if target_path == self.workspace_dir:
            raise FileAccessDeniedError("Cannot write to workspace root as a file.")

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self.max_write_bytes:
            raise FileTooLargeError(
                f"Content exceeds the {self.max_write_bytes}-byte write limit."
            )

        created = not target_path.exists()
        if not created and not overwrite:
            raise FileOperationError(f"File '{relative_path}' already exists and overwrite=False.")

        if target_path.exists() and target_path.is_dir():
            raise FileOperationError(f"Path '{relative_path}' is a directory, not a file.")

        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            target_path.write_text(content, encoding="utf-8")
            bytes_written = len(content_bytes)
            result = FileWriteResult(
                path=self._get_relative_str(target_path),
                bytes_written=bytes_written,
                created=created,
            )
            event_name: Literal["files.created", "files.overwritten"] = (
                "files.created" if created else "files.overwritten"
            )
            self.event_bus.publish(event_name, {"path": result.path, "bytes_written": bytes_written})
            return result
        except FileOperationError:
            raise
        except OSError as err:
            raise FileOperationError(f"Failed to write file '{relative_path}': {err}")

    def delete_file(self, relative_path: str) -> bool:
        """Delete a file or directory inside the workspace."""
        target_path = self.resolve_and_validate_path(relative_path)

        if target_path == self.workspace_dir:
            raise FileAccessDeniedError("Cannot delete workspace root directory.")

        if not target_path.exists():
            raise FileNotFoundInWorkspaceError(
                f"Path '{relative_path}' not found in workspace."
            )

        try:
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
            self.event_bus.publish("files.deleted", {"path": self._get_relative_str(target_path)})
            return True
        except OSError as err:
            raise FileOperationError(f"Failed to delete '{relative_path}': {err}")

    def search_files(self, query: str, sub_path: str = "") -> list[FileInfo]:
        """Search for files matching query in filename or text content."""
        all_items = self.list_files(sub_path)
        q = query.lower()
        results: list[FileInfo] = []

        for item in all_items:
            # Check filename match
            if q in item.path.lower():
                results.append(item)
                continue

            # Check content match for files
            if not item.is_directory:
                try:
                    read_res = self.read_file(item.path)
                    if q in read_res.content.lower():
                        results.append(item)
                except (FileOperationError, FileTooLargeError, UnsupportedFileTypeError):
                    continue

            if len(results) >= self.max_results:
                break

        return results
