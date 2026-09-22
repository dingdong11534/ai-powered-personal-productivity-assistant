"""Custom exception types for the Files domain."""


class FileOperationError(Exception):
    """Base exception for file operation failures."""


class FileAccessDeniedError(FileOperationError):
    """Raised when a path traversal attempt or unauthorized path outside the sandbox is accessed."""


class FileNotFoundInWorkspaceError(FileOperationError):
    """Raised when a requested file or directory does not exist within the workspace sandbox."""


class FileTooLargeError(FileOperationError):
    """Raised when a file operation would exceed the configured size limit."""


class UnsupportedFileTypeError(FileOperationError):
    """Raised when an operation encounters binary rather than UTF-8 text data."""
