"""
FastAPI REST API for SimStackServer File Operations

This module provides REST endpoints for file and directory operations
that mirror the functionality from ClusterManager.py
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Pydantic models for request/response


class FilePathRequest(BaseModel):
    """Identify a file on the server by its path relative to the basepath."""

    filename: str = Field(
        ...,
        description="Path to the file, **relative to the server basepath** (e.g. `singlejobs/{uid}/output.yml`).",
    )
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath (advanced; omit for normal use)."
    )


class DirectoryPathRequest(BaseModel):
    """Model for directory path operations"""

    dirname: str = Field(..., description="Path to the directory")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )


class MkdirRequest(BaseModel):
    """Model for creating directories"""

    directory: str = Field(..., description="Directory path to create")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )
    mode_override: Optional[int] = Field(
        None, description="Permission mode (e.g., 0o770)"
    )


class ListDirRequest(BaseModel):
    """Identify a directory to list, relative to the server basepath."""

    path: str = Field(
        ...,
        description=(
            "Directory path relative to the server basepath.  "
            "Examples: `singlejobs/{job_uid}`, `my_workflow/workflow_data/Step1/outputs`."
        ),
    )
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath (advanced; omit for normal use)."
    )


class FileInfo(BaseModel):
    """One entry in a directory listing."""

    name: str = Field(..., description="Filename or subdirectory name.")
    path: str = Field(..., description="Absolute path of the parent directory on the server.")
    type: str = Field(..., description='`"f"` for a regular file, `"d"` for a directory.')


class ListDirResponse(BaseModel):
    """Directory listing returned by `/api/files/list`."""

    files: List[FileInfo] = Field(..., description="Entries in the directory.")
    count: int = Field(..., description="Number of entries.")


class ExistsResponse(BaseModel):
    """Model for existence check response"""

    exists: bool
    path: str
    is_directory: Optional[bool] = None


class DeleteResponse(BaseModel):
    """Model for delete operation response"""

    deleted: bool
    path: str
    message: str


class MkdirResponse(BaseModel):
    """Model for mkdir operation response"""

    created: bool
    path: str
    absolute_path: str


class UploadFileRequest(BaseModel):
    """Model for file upload request"""

    to_file: str = Field(..., description="Destination path on server")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )


class DownloadFileRequest(BaseModel):
    """Model for file download request"""

    from_file: str = Field(..., description="Source path on server")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )


class PutDirectoryRequest(BaseModel):
    """Model for directory upload request"""

    from_directory: str = Field(..., description="Local directory path")
    to_directory: str = Field(..., description="Destination directory path on server")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )


class GetDirectoryRequest(BaseModel):
    """Model for directory download request"""

    from_directory_on_server: str = Field(
        ..., description="Source directory path on server"
    )
    to_directory: str = Field(..., description="Local destination directory path")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )


class FileOperationResponse(BaseModel):
    """Generic file operation response"""

    success: bool
    message: str
    path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ExternalInputFileInfo(BaseModel):
    """Describes a single user-supplied file that a WaNo requires."""

    logical_name: str = Field(..., description="Logical filename used inside the WaNo")
    source_path: str = Field(
        ...,
        description="Current value / hint for the expected source path on the client",
    )


class WanoRequiredFilesRequest(BaseModel):
    """Request body for the required-files endpoint."""

    wano_spec: Dict[str, Any] = Field(
        ..., description="WaNo spec dict as produced by WaNoModelRoot.to_spec()"
    )


class WanoRequiredFilesResponse(BaseModel):
    """Lists external input files that the user must upload before job execution."""

    wano_name: str
    external_input_files: List[ExternalInputFileInfo]


# ---------------------------------------------------------------------------
# Workflow-level upload manifest
# ---------------------------------------------------------------------------


class WorkflowNodeSpec(BaseModel):
    """One WaNo node in a workflow, identified by its spec and DAG path."""

    wano_spec: Dict[str, Any] = Field(
        ..., description="WaNo spec dict as produced by WaNoModelRoot.to_spec()"
    )
    wfem_path: str = Field(
        ...,
        description='Path of this node in the workflow DAG, e.g. "Step1" or "ForEach/0/MyWaNo"',
    )


class UploadItemResponse(BaseModel):
    """Describes one file that must (or will be) present on the server."""

    server_path: str = Field(
        ..., description="Destination path on server, relative to storage"
    )
    logical_name: str = Field(
        ..., description="Filename as seen inside the job directory"
    )
    wfem_name: str = Field(..., description="Name of the WaNo that requires this file")
    wfem_path: str = Field(..., description="Path of the WaNo node in the workflow DAG")
    category: str = Field(
        ...,
        description=(
            '"wano_definition" = generated automatically, no user action needed; '
            '"external_input" = user must supply this file'
        ),
    )
    local_source: Optional[str] = Field(
        None, description="Hint for the local source path"
    )
    required: bool = Field(True, description="False if the file is optional")


class WorkflowRequiredFilesRequest(BaseModel):
    """Request body for the workflow-level required-files endpoint."""

    nodes: List[WorkflowNodeSpec] = Field(
        ..., description="All WaNo nodes in the workflow, each with its DAG path"
    )


class WorkflowRequiredFilesResponse(BaseModel):
    """Upload manifest for a full workflow.

    Splits items into ``wano_definition`` (auto-handled) and ``external_input``
    (user must provide) so the caller can focus only on what they need to supply.
    """

    all_items: List[UploadItemResponse]
    required_user_uploads: List[UploadItemResponse] = Field(
        ..., description="Subset of all_items where category == external_input"
    )
    wano_definition_items: List[UploadItemResponse] = Field(
        ..., description="Subset of all_items where category == wano_definition"
    )
    summary: str = Field(..., description="Human-readable summary of the manifest")
