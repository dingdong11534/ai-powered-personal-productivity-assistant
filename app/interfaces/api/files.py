"""FastAPI router for workspace file operations."""

from fastapi import APIRouter, Query, status

from app.core.permissions import PermissionChecker, PermissionRequest, PermissionScope
from app.files.schemas import FileInfo, FileReadResult, FileWriteRequest, FileWriteResult
from app.files.service import FileService

router = APIRouter(prefix="/files", tags=["Files"])


def get_file_service() -> FileService:
    return FileService()


def _authorize(scope: PermissionScope, description: str, authorized: bool = False) -> None:
    """Use the shared permission boundary for direct user API operations."""
    PermissionChecker().check(
        PermissionRequest(scope=scope, actor="api", description=description, authorized=authorized)
    )


@router.get("", response_model=list[FileInfo])
def list_workspace_files(
    sub_path: str = Query(default="", description="Subdirectory path inside workspace"),
    search: str | None = Query(default=None, description="Optional search query filter"),
):
    svc = get_file_service()
    if search:
        return svc.search_files(query=search, sub_path=sub_path)
    return svc.list_files(sub_path=sub_path)


@router.get("/read", response_model=FileReadResult)
def read_workspace_file(
    path: str = Query(..., description="Relative file path in workspace"),
):
    svc = get_file_service()
    return svc.read_file(relative_path=path)


@router.post("/write", response_model=FileWriteResult, status_code=status.HTTP_201_CREATED)
def write_workspace_file(req: FileWriteRequest):
    svc = get_file_service()
    is_overwrite = svc.resolve_and_validate_path(req.path).exists()
    _authorize(
        PermissionScope.DESTRUCTIVE if is_overwrite else PermissionScope.WRITE,
        f"write workspace file {req.path!r}",
        authorized=req.confirm_destructive,
    )
    return svc.write_file(
        relative_path=req.path,
        content=req.content,
        overwrite=req.overwrite,
    )


@router.delete("")
def delete_workspace_file(
    path: str = Query(..., description="Relative file or folder path in workspace to delete"),
    confirm_destructive: bool = Query(
        default=False,
        description="Explicit confirmation required before deleting a workspace path.",
    ),
):
    svc = get_file_service()
    _authorize(
        PermissionScope.DESTRUCTIVE,
        f"delete workspace path {path!r}",
        authorized=confirm_destructive,
    )
    svc.delete_file(relative_path=path)
    return {"success": True, "message": f"Path '{path}' deleted successfully."}
