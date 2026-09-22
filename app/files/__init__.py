"""Files domain module for sandboxed assistant workspace operations."""

from app.files.exceptions import (
    FileAccessDeniedError,
    FileNotFoundInWorkspaceError,
    FileOperationError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.files.schemas import FileInfo, FileReadResult, FileWriteRequest, FileWriteResult
from app.files.service import FileService

__all__ = [
    "FileAccessDeniedError",
    "FileNotFoundInWorkspaceError",
    "FileOperationError",
    "FileTooLargeError",
    "UnsupportedFileTypeError",
    "FileInfo",
    "FileReadResult",
    "FileWriteRequest",
    "FileWriteResult",
    "FileService",
]
