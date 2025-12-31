"""
FastAPI REST API for SimStackServer File Operations

This module provides REST endpoints for file and directory operations
that mirror the functionality from ClusterManager.py
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Pydantic models for request/response


class FilePathRequest(BaseModel):
    """Model for file path operations"""

    filename: str = Field(..., description="Path to the file")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
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
    """Model for listing directory contents"""

    path: str = Field(..., description="Directory path to list")
    basepath_override: Optional[str] = Field(
        None, description="Override the default basepath"
    )


class FileInfo(BaseModel):
    """Model for file information"""

    name: str
    path: str
    type: str  # 'f' for file, 'd' for directory


class ListDirResponse(BaseModel):
    """Model for directory listing response"""

    files: List[FileInfo]
    count: int


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
