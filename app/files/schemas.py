"""Pydantic schemas for the Files domain."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class FileInfo(BaseModel):
    """Metadata describing a file or directory inside the sandboxed workspace."""

    model_config = ConfigDict(from_attributes=True)

    path: str = Field(description="Relative path within the workspace.")
    size: int = Field(description="File size in bytes (0 for directories).")
    is_directory: bool = Field(description="True if path is a directory.")
    modified_at: datetime = Field(description="Timestamp of last modification.")


class FileReadResult(BaseModel):
    """Result of reading a file's content from the workspace."""

    model_config = ConfigDict(from_attributes=True)

    path: str = Field(description="Relative path within the workspace.")
    content: str = Field(description="Text content of the file.")
    size: int = Field(description="Size of the file in bytes.")


class FileWriteRequest(BaseModel):
    """Request payload for writing/creating a file in the workspace."""

    path: str = Field(description="Relative target path within the workspace.")
    content: str = Field(description="Text content to write into the file.")
    overwrite: bool = Field(default=True, description="Whether to overwrite if file already exists.")
    confirm_destructive: bool = Field(
        default=False,
        description="Explicit user confirmation required when overwrite replaces an existing file.",
    )


class FileWriteResult(BaseModel):
    """Result of writing a file into the workspace."""

    model_config = ConfigDict(from_attributes=True)

    path: str = Field(description="Relative path within the workspace.")
    bytes_written: int = Field(description="Number of bytes written.")
    created: bool = Field(description="True if a new file was created, False if overwritten.")
