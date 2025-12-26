import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Optional
import tempfile
import os

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from SimStackServer.REST.files_api import (
    FilePathRequest,
    DirectoryPathRequest,
    MkdirRequest,
    ListDirRequest,
    ListDirResponse,
    ExistsResponse,
    DeleteResponse,
    MkdirResponse,
    FileOperationResponse,
    FileInfo,
)
from SimStackServer.WorkflowModel import WorkflowExecModule

if TYPE_CHECKING:
    from SimStackServer.SimStackServerMain import SimStackServer


# Request/Response models for workflow operations
class SubmitWorkflowRequest(BaseModel):
    """Request model for workflow submission"""
    filename: str


class SubmitWorkflowResponse(BaseModel):
    """Response model for workflow submission"""
    status: str
    message: str
    filename: str


class SubmitSingleJobRequest(BaseModel):
    """Request model for single job submission"""
    wfem: dict


class SubmitSingleJobResponse(BaseModel):
    """Response model for single job submission"""
    status: str
    message: str
    job_uid: str


class HTTPServerInfo(BaseModel):
    """HTTP server information"""
    port: int
    user: str
    password: str
    url: str


class HTTPServerRequest(BaseModel):
    """Request for HTTP server info"""
    basefolder: str


class ShutdownResponse(BaseModel):
    """Response for shutdown request"""
    status: str
    message: str


class FastAPIThread(threading.Thread):
    """Thread to run FastAPI server for SimStackServer REST API"""

    def __init__(self, simstack_server: "SimStackServer", host="127.0.0.1", port=8000):
        super().__init__(name="FastAPI-Thread", daemon=True)
        self.simstack_server = simstack_server
        self.host = host
        self.port = port
        self.server = None
        self._logger = logging.getLogger("FastAPIThread")

        # Create FastAPI app
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            self._logger.info("FastAPI starting up")
            yield
            # Shutdown
            self._logger.info("FastAPI shutting down")

        self.app = FastAPI(
            title="SimStackServer API",
            description="REST API for SimStackServer workflow management",
            version="1.0.0",
            lifespan=lifespan,
        )
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes with access to SimStackServer"""

        @self.app.get("/")
        async def root():
            """Root endpoint - service information"""
            return {
                "status": "running",
                "service": "SimStackServer",
                "api_version": "1.0.0",
            }

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "workflows_running": self.simstack_server._workflow_manager.workflows_running(),
            }

        @self.app.get("/api/workflows")
        async def list_workflows():
            """List all workflows (in-progress and finished)"""
            try:
                inprogress = (
                    self.simstack_server._workflow_manager.get_inprogress_workflows()
                )
                finished = (
                    self.simstack_server._workflow_manager.get_finished_workflows()
                )
                return {
                    "inprogress": inprogress,
                    "finished": finished,
                    "total": len(inprogress) + len(finished),
                }
            except Exception as e:
                self._logger.exception("Error listing workflows")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/workflows/inprogress")
        async def list_inprogress_workflows():
            """List in-progress workflows"""
            try:
                workflows = (
                    self.simstack_server._workflow_manager.get_inprogress_workflows()
                )
                return {"workflows": workflows, "count": len(workflows)}
            except Exception as e:
                self._logger.exception("Error listing in-progress workflows")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/workflows/finished")
        async def list_finished_workflows():
            """List finished workflows"""
            try:
                workflows = (
                    self.simstack_server._workflow_manager.get_finished_workflows()
                )
                return {"workflows": workflows, "count": len(workflows)}
            except Exception as e:
                self._logger.exception("Error listing finished workflows")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/workflows/{workflow_id}/jobs")
        async def list_workflow_jobs(workflow_id: str):
            """List jobs for a specific workflow"""
            try:
                jobs = self.simstack_server._workflow_manager.list_jobs_of_workflow(
                    workflow_id
                )
                return {"workflow_id": workflow_id, "jobs": jobs, "count": len(jobs)}
            except Exception as e:
                self._logger.exception(f"Error listing jobs for workflow {workflow_id}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/workflows/{workflow_id}/abort")
        async def abort_workflow(workflow_id: str):
            """Abort a specific workflow"""
            try:
                self.simstack_server._workflow_manager.abort_workflow(workflow_id)
                self._logger.info(f"Workflow {workflow_id} abort requested via API")
                return {
                    "status": "abort_requested",
                    "workflow_id": workflow_id,
                    "message": "Workflow abort has been requested",
                }
            except Exception as e:
                self._logger.exception(f"Error aborting workflow {workflow_id}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/api/workflows/{workflow_id}")
        async def delete_workflow(workflow_id: str):
            """Delete a workflow"""
            try:
                self.simstack_server._workflow_manager.delete_workflow(workflow_id)
                self._logger.info(f"Workflow {workflow_id} deletion requested via API")
                return {
                    "status": "deleted",
                    "workflow_id": workflow_id,
                    "message": "Workflow deletion has been requested",
                }
            except Exception as e:
                self._logger.exception(f"Error deleting workflow {workflow_id}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/singlejobs/{job_uid}/status")
        async def get_singlejob_status(job_uid: str):
            """Get status of a single job"""
            try:
                status = self.simstack_server._workflow_manager.get_singlejob_status(
                    job_uid
                )
                return {"job_uid": job_uid, "status": status}
            except Exception as e:
                self._logger.exception(f"Error getting status for job {job_uid}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/singlejobs/{job_uid}/abort")
        async def abort_singlejob(job_uid: str):
            """Abort a single job"""
            try:
                self.simstack_server._workflow_manager.abort_singlejob(job_uid)
                self._logger.info(f"Single job {job_uid} abort requested via API")
                return {
                    "status": "abort_requested",
                    "job_uid": job_uid,
                    "message": "Job abort has been requested",
                }
            except Exception as e:
                self._logger.exception(f"Error aborting single job {job_uid}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/workflows/submit", response_model=SubmitWorkflowResponse)
        async def submit_workflow(request: SubmitWorkflowRequest):
            """Submit a workflow for execution"""
            try:
                # Convert relative path to absolute path
                workflow_filename = self.simstack_server._remote_relative_to_absolute_filename(
                    request.filename
                )

                self._logger.info(f"Workflow submission requested: {workflow_filename}")

                # Add to submission queue
                self.simstack_server._submitted_workflow_queue.put(workflow_filename)

                return SubmitWorkflowResponse(
                    status="submitted",
                    message="Workflow has been submitted for execution",
                    filename=request.filename
                )
            except Exception as e:
                self._logger.exception(f"Error submitting workflow: {request.filename}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/singlejobs/submit", response_model=SubmitSingleJobResponse)
        async def submit_singlejob(request: SubmitSingleJobRequest):
            """Submit a single job for execution"""
            try:
                # Create WorkflowExecModule from dict
                wfem = WorkflowExecModule()
                wfem.from_dict(request.wfem)

                self._logger.info(f"Single job submission requested: {wfem.uid}")

                # Add to submission queue
                self.simstack_server._submitted_singlejob_queue.put(wfem)
                self.simstack_server._external_job_uid_to_jobid[wfem.uid] = -1

                return SubmitSingleJobResponse(
                    status="submitted",
                    message="Single job has been submitted for execution",
                    job_uid=wfem.uid
                )
            except Exception as e:
                self._logger.exception("Error submitting single job")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/http-server", response_model=HTTPServerInfo)
        async def get_http_server(request: HTTPServerRequest):
            """Get or start HTTP server for serving files"""
            try:
                # Check if HTTP server is already running
                if not self.simstack_server._http_server or not self.simstack_server._http_server.is_alive():
                    user, mypass, port = self.simstack_server._start_http_server(
                        directory=request.basefolder
                    )
                    self.simstack_server._http_user = user
                    self.simstack_server._http_pass = mypass
                    self.simstack_server._http_port = port
                else:
                    user = self.simstack_server._http_user
                    mypass = self.simstack_server._http_pass
                    port = self.simstack_server._http_port

                return HTTPServerInfo(
                    port=port,
                    user=user,
                    password=mypass,
                    url=f"http://{user}:{mypass}@localhost:{port}"
                )
            except Exception as e:
                self._logger.exception("Error getting HTTP server info")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/server/shutdown", response_model=ShutdownResponse)
        async def shutdown_server():
            """Shutdown the SimStackServer"""
            try:
                self._logger.info("Server shutdown requested via API")
                self.simstack_server._stop_main = True
                self.simstack_server._stop_thread = True

                return ShutdownResponse(
                    status="shutting_down",
                    message="Server shutdown has been initiated"
                )
            except Exception as e:
                self._logger.exception("Error during server shutdown")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/server/clear-state")
        async def clear_server_state():
            """Clear server state (for testing)"""
            try:
                self._logger.info("Hard clearing server state via API")
                self.simstack_server._clear_server_state()

                return {
                    "status": "cleared",
                    "message": "Server state has been cleared"
                }
            except Exception as e:
                self._logger.exception("Error clearing server state")
                raise HTTPException(status_code=500, detail=str(e))

        # File Operations API

        @self.app.post("/api/files/exists", response_model=ExistsResponse)
        async def check_file_exists(request: FilePathRequest):
            """Check if a file or directory exists"""
            try:
                filepath = self._resolve_path(request.filename, request.basepath_override)
                exists = os.path.exists(filepath)
                is_dir = os.path.isdir(filepath) if exists else None
                return ExistsResponse(
                    exists=exists,
                    path=request.filename,
                    is_directory=is_dir
                )
            except Exception as e:
                self._logger.exception(f"Error checking if file exists: {request.filename}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/files/list", response_model=ListDirResponse)
        async def list_directory(request: ListDirRequest):
            """List contents of a directory"""
            try:
                dirpath = self._resolve_path(request.path, request.basepath_override)

                if not os.path.exists(dirpath):
                    raise HTTPException(status_code=404, detail=f"Directory not found: {request.path}")

                if not os.path.isdir(dirpath):
                    raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

                files = []
                for entry in os.listdir(dirpath):
                    entry_path = os.path.join(dirpath, entry)
                    file_type = 'd' if os.path.isdir(entry_path) else 'f'
                    files.append(FileInfo(
                        name=entry,
                        path=dirpath,
                        type=file_type
                    ))

                return ListDirResponse(files=files, count=len(files))
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error listing directory: {request.path}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/files/mkdir", response_model=MkdirResponse)
        async def create_directory(request: MkdirRequest):
            """Create a directory (recursively)"""
            try:
                dirpath = self._resolve_path(request.directory, request.basepath_override)

                if os.path.exists(dirpath):
                    if not os.path.isdir(dirpath):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Path exists but is not a directory: {request.directory}"
                        )
                    return MkdirResponse(
                        created=False,
                        path=request.directory,
                        absolute_path=dirpath
                    )

                os.makedirs(dirpath, mode=request.mode_override or 0o770, exist_ok=True)
                self._logger.info(f"Created directory: {dirpath}")

                return MkdirResponse(
                    created=True,
                    path=request.directory,
                    absolute_path=dirpath
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error creating directory: {request.directory}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/api/files/delete", response_model=DeleteResponse)
        async def delete_file(request: FilePathRequest):
            """Delete a file"""
            try:
                filepath = self._resolve_path(request.filename, request.basepath_override)

                if not os.path.exists(filepath):
                    raise HTTPException(status_code=404, detail=f"File not found: {request.filename}")

                if os.path.isdir(filepath):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path is a directory, use /api/files/rmtree instead: {request.filename}"
                    )

                os.remove(filepath)
                self._logger.info(f"Deleted file: {filepath}")

                return DeleteResponse(
                    deleted=True,
                    path=request.filename,
                    message="File deleted successfully"
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error deleting file: {request.filename}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/api/files/rmtree", response_model=DeleteResponse)
        async def remove_directory_tree(request: DirectoryPathRequest):
            """Delete a directory and all its contents recursively"""
            try:
                dirpath = self._resolve_path(request.dirname, request.basepath_override)

                if not os.path.exists(dirpath):
                    # Silently succeed if directory doesn't exist (like ClusterManager.rmtree)
                    return DeleteResponse(
                        deleted=False,
                        path=request.dirname,
                        message="Directory does not exist"
                    )

                if not os.path.isdir(dirpath):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path is not a directory: {request.dirname}"
                    )

                import shutil
                shutil.rmtree(dirpath)
                self._logger.info(f"Deleted directory tree: {dirpath}")

                return DeleteResponse(
                    deleted=True,
                    path=request.dirname,
                    message="Directory deleted successfully"
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error deleting directory: {request.dirname}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/files/upload")
        async def upload_file(
            file: UploadFile = File(...),
            to_file: Optional[str] = Form(None),
            basepath_override: Optional[str] = Form(None)
        ):
            """Upload a file to the server"""
            try:
                # Use the provided path or fall back to the original filename
                destination = to_file if to_file else file.filename

                filepath = self._resolve_path(destination, basepath_override)

                # Create directory if it doesn't exist
                dir_path = os.path.dirname(filepath)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)

                # Write file
                with open(filepath, "wb") as f:
                    content = await file.read()
                    f.write(content)

                self._logger.info(f"Uploaded file: {filepath}")

                return FileOperationResponse(
                    success=True,
                    message="File uploaded successfully",
                    path=destination
                )
            except Exception as e:
                self._logger.exception(f"Error uploading file to: {to_file}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/files/download")
        async def download_file(
            from_file: str,
            basepath_override: Optional[str] = None
        ):
            """Download a file from the server"""
            try:
                filepath = self._resolve_path(from_file, basepath_override)

                if not os.path.exists(filepath):
                    raise HTTPException(status_code=404, detail=f"File not found: {from_file}")

                if os.path.isdir(filepath):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path is a directory: {from_file}"
                    )

                return FileResponse(
                    filepath,
                    filename=os.path.basename(filepath),
                    media_type='application/octet-stream'
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error downloading file: {from_file}")
                raise HTTPException(status_code=500, detail=str(e))

    def _resolve_path(self, path: str, basepath_override: Optional[str] = None) -> str:
        """
        Resolve a path relative to the calculation basepath

        Args:
            path: The relative path
            basepath_override: Optional override for the basepath

        Returns:
            Absolute path
        """
        if basepath_override is None:
            # Get basepath from config if available
            if self.simstack_server._config:
                basepath = self.simstack_server._config.get_calculation_basepath()
            else:
                basepath = os.getcwd()
        else:
            basepath = basepath_override

        # Remove leading slash if present
        if path.startswith("/"):
            path = path[1:]

        return os.path.join(basepath, path)

    def run(self):
        """Run the uvicorn server"""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False,  # Use existing logging system
        )
        self.server = uvicorn.Server(config)
        self._logger.info(f"Starting FastAPI server on {self.host}:{self.port}")
        self.server.run()

    def shutdown(self):
        """Gracefully shutdown the server"""
        if self.server:
            self._logger.info("Shutting down FastAPI server")
            self.server.should_exit = True
