import logging
import secrets
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Optional
import os
import datetime
import html
import urllib.parse
import sys
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

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
    ExternalInputFileInfo,
    WanoRequiredFilesRequest,
    WanoRequiredFilesResponse,
    WorkflowRequiredFilesRequest,
    WorkflowRequiredFilesResponse,
    UploadItemResponse,
)
from SimStackServer.WorkflowModel import WorkflowExecModule, Resources
from SimStackServer.Config import Config
import SimStackServer.Data as DataDir

if TYPE_CHECKING:
    from SimStackServer.SimStackServerMain import SimStackServer


# Request/Response models for workflow operations
class SubmitWorkflowRequest(BaseModel):
    """Submit a previously uploaded workflow for execution."""

    filename: str = Field(
        ...,
        description=(
            "Path to `rendered_workflow.xml` **relative to the server basepath**. "
            "The file and the accompanying `workflow_data/` tree must already "
            "have been uploaded via `/api/files/upload`."
        ),
        json_schema_extra={
            "examples": ["my_workflow_2024-01-01/rendered_workflow.xml"]
        },
    )


class SubmitWorkflowResponse(BaseModel):
    """Acknowledgement that a workflow has been queued for execution."""

    status: str = Field(..., description='Always `"submitted"` on success.')
    message: str
    filename: str = Field(..., description="Echo of the submitted filename.")


class SubmitSingleJobRequest(BaseModel):
    """Submit a self-contained single job for execution.

    The `wfem` dict is a serialised `WorkflowExecModule` — typically produced
    by calling `wfem.to_dict(d)` on a WFEM built with
    `WaNoModelRoot.build_wfem_with_bundle()`.  It contains all WaNo definition
    files as base64-encoded entries, so no prior file upload is needed for the
    WaNo itself.  External user-supplied files (e.g. from `<WaNoFile>` parameters)
    must still be uploaded separately via `/api/files/upload` before submission.
    """

    wfem: dict = Field(
        ...,
        description=(
            "Serialised WorkflowExecModule dict.  Must include at minimum: "
            "`uid`, `exec_command`, `inputs`, `outputs`, `resources`, "
            "and (for bundle jobs) `wano_bundle`."
        ),
    )


class SubmitSingleJobResponse(BaseModel):
    """Acknowledgement that a single job has been queued for execution."""

    status: str = Field(..., description='Always `"submitted"` on success.')
    message: str
    job_uid: str = Field(
        ...,
        description="Unique identifier for this job.  Use it to poll status via "
        "`GET /api/singlejobs/{job_uid}/status`.",
    )


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


class ConfigureRequest(BaseModel):
    """Request model for configuration"""

    resources: dict


class ConfigureResponse(BaseModel):
    """Response model for configuration"""

    status: str
    message: str


class FastAPIThread(threading.Thread):
    """Thread to run FastAPI server for SimStackServer REST API"""

    # Custom MIME type mappings (same as HTTPServer)
    CUSTOM_MIME_TYPES = {
        ".lsf": "text/plain",
        ".body": "text/plain",
        ".ini": "text/plain",
        ".stderr": "text/plain",
        ".stdout": "text/plain",
        ".sh": "text/plain",
        ".yml": "text/plain",
        ".json": "text/plain",
        ".dat": "text/plain",
        ".txt": "text/plain",
        ".sge": "text/plain",
        ".log": "text/plain",
        ".script": "text/plain",
        ".pbs": "text/plain",
        ".slr": "text/plain",
        "": "text/plain",
    }

    def __init__(
        self,
        simstack_server: "SimStackServer",
        host="127.0.0.1",
        port=8000,
        use_https=True,
        cert_dir: Optional[Path] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        super().__init__(name="FastAPI-Thread", daemon=True)
        self.simstack_server = simstack_server
        self.host = host
        self.port = port
        self.server = None
        self._logger = logging.getLogger("FastAPIThread")
        self.use_https = use_https
        self.ssl_keyfile: Optional[str] = None
        self.ssl_certfile: Optional[str] = None

        # Setup SSL certificates if HTTPS is enabled
        if self.use_https:
            self._setup_ssl_certificates(cert_dir)

        # Build global auth dependency when credentials are provided
        global_dependencies = []
        if username and password:
            _security = HTTPBasic()
            _username = username
            _password = password

            async def _verify_credentials(
                credentials: HTTPBasicCredentials = Depends(_security),
            ):
                correct_username = secrets.compare_digest(
                    credentials.username.encode("utf-8"), _username.encode("utf-8")
                )
                correct_password = secrets.compare_digest(
                    credentials.password.encode("utf-8"), _password.encode("utf-8")
                )
                if not (correct_username and correct_password):
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid credentials",
                        headers={"WWW-Authenticate": "Basic"},
                    )

            global_dependencies = [Depends(_verify_credentials)]

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
            description="""\
REST API for the SimStack scientific-workflow execution server.

## Core concepts

| Concept | Description |
|---------|-------------|
| **WaNo** | *Workflow Active Node* — a reusable computational step defined by an XML file, input/output declarations, and an exec command. |
| **WFEM** | *WorkflowExecModule* — the runtime representation of a single WaNo step, including its parameters, resource requirements, stage-in/out file lists, and (optionally) a base64-encoded file bundle. |
| **Workflow** | A directed acyclic graph (DAG) of WFEMs, serialised as `rendered_workflow.xml`. |
| **Basepath** | A server-side root directory (default `~/simstack_workspace`).  **All paths accepted and returned by the API are relative to this basepath** unless stated otherwise. |

## Submission modes

### 1. Single job (bundle API)
Build a self-contained WFEM on the client (all WaNo files embedded as base64),
then submit it in one call.  The server unpacks the bundle, renders the WaNo,
and executes the job.

**Typical flow:**

1. `GET /health` — verify server is reachable.
2. Build a WFEM dict on the client (see `WaNoModelRoot.build_wfem_with_bundle()`).
3. *(optional)* `POST /api/files/upload` — upload any external input files that
   are not part of the bundle (e.g. user-supplied scientific data).
4. `POST /api/singlejobs/submit` — submit the WFEM dict.
5. `GET /api/singlejobs/{job_uid}/status` — poll until `status.status == "finished"`.
6. `POST /api/files/list` — list output files under `singlejobs/{job_uid}/`.

### 2. Multi-step workflow (DSL / XML)
Compose multiple steps into a DAG, upload the staging directory and
`rendered_workflow.xml`, then submit.

**Typical flow:**

1. `GET /health` — verify server is reachable.
2. Build the workflow on the client (e.g. via `WorkflowDSL`). This produces a
   staging directory with `workflow_data/<StepName>/inputs/…` for each step, plus
   a `rendered_workflow.xml`.
3. `POST /api/files/upload` — upload every file from the staging directory.
   Use `to_file` to set the relative path under the basepath
   (e.g. `my_workflow_2024-01-01/workflow_data/Step1/inputs/config.xml`).
4. `POST /api/files/upload` — upload `rendered_workflow.xml` to
   `my_workflow_2024-01-01/rendered_workflow.xml`.
5. `POST /api/workflows/submit` — submit with
   `{"filename": "my_workflow_2024-01-01/rendered_workflow.xml"}`.
6. `GET /api/workflows/inprogress` / `GET /api/workflows/finished` — poll until
   the workflow name appears in the finished list.
7. `POST /api/files/list` — list results under `my_workflow_2024-01-01/`.

## Authentication

When the server is started with `--username` and `--password`, all endpoints
require HTTP Basic authentication.  Swagger UI's *Authorize* button can be
used to set credentials for interactive testing.
""",
            version="1.0.0",
            lifespan=lifespan,
            dependencies=global_dependencies,
        )
        self._setup_routes()

    def _setup_ssl_certificates(self, cert_dir: Optional[Path] = None) -> None:
        """
        Setup SSL certificates for HTTPS support using fastapilocalhttps.

        Args:
            cert_dir: Optional directory to store certificates. If None, uses ~/.simstack/certs
        """
        try:
            from fastapilocalhttps import CertificateManager
        except ImportError as e:
            self._logger.error(
                "Failed to import fastapilocalhttps. "
                "Please ensure fastapilocalhttps and its dependencies (structlog, cryptography) are installed."
            )
            raise ImportError(
                "fastapilocalhttps is required for HTTPS support. "
                "Install it with: pixi add fastapilocalhttps structlog"
            ) from e

        # Determine certificate directory
        if cert_dir is None:
            home_dir = Path.home()
            cert_dir = home_dir / ".simstack" / "certs"
            cert_dir.mkdir(parents=True, exist_ok=True)

        # Setup certificate manager
        cert_manager = CertificateManager(
            cert_dir=cert_dir,
            hostname=self.host if self.host not in ["0.0.0.0", ""] else "localhost",
            san_dns_names=["localhost"],
            san_ip_addresses=["127.0.0.1", self.host]
            if self.host not in ["0.0.0.0", ""]
            else ["127.0.0.1"],
            key_size=2048,
            validity_days=365,
        )

        # Generate or get existing certificates
        if not cert_manager.certificate_exists():
            key_path, cert_path = cert_manager.generate_certificate()
            self._logger.info(f"Generated self-signed SSL certificates at {cert_dir}")
        else:
            key_path, cert_path = cert_manager.get_certificate_paths()
            self._logger.info(f"Using existing SSL certificates from {cert_dir}")

        # Store certificate paths
        self.ssl_keyfile = str(key_path)
        self.ssl_certfile = str(cert_path)

    @staticmethod
    def _get_static_http_path():
        """Get path to static HTTP files (favicon, CSS)"""
        data_dir = os.path.join(
            os.path.dirname(os.path.realpath(DataDir.__file__)), "static_http"
        )
        return data_dir

    @staticmethod
    def _human_readable_size(size: int, decimal_places: int = 2) -> str:
        """Convert bytes to human readable format"""
        for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
            if size < 1024.0:
                break
            size /= 1024.0
        return f"{size:.{decimal_places}f}{unit}"

    @staticmethod
    def _guess_mime_type(filename: str) -> str:
        """Guess MIME type based on file extension"""
        import mimetypes

        # Get file extension
        _, ext = os.path.splitext(filename)

        # Check custom types first
        if ext in FastAPIThread.CUSTOM_MIME_TYPES:
            return FastAPIThread.CUSTOM_MIME_TYPES[ext]

        # Fall back to standard mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def _generate_directory_listing_html(self, path: str, display_path: str) -> str:
        """Generate HTML directory listing (similar to HTTPServer)"""
        try:
            entries = os.listdir(path)
        except OSError:
            raise HTTPException(
                status_code=404, detail="No permission to list directory"
            )

        entries.sort(key=lambda a: a.lower())

        # HTML escape the display path
        display_path_escaped = html.escape(display_path, quote=False)
        enc = sys.getfilesystemencoding()
        title = f"Directory listing for {display_path_escaped}"

        # Build HTML
        html_parts = []
        html_parts.append(
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
            '"http://www.w3.org/TR/html4/strict.dtd">'
        )
        html_parts.append("<html>\n<head>")
        html_parts.append('<link rel="stylesheet" href="/http/static/dirlist.css" />')
        html_parts.append(
            f'<meta http-equiv="Content-Type" content="text/html; charset={enc}">'
        )
        html_parts.append(f"<title>{title}</title>\n</head>")
        html_parts.append(f"<body>\n<br/><center><b>Index of {title}</b></center><br/>")
        html_parts.append('<div class="list">')
        html_parts.append(
            '<table summary="Directory Listing" cellpadding="0" cellspacing="0">'
        )
        html_parts.append(
            '<thead><tr><th class="n">Name</th><th class="m">Last Modified</th>'
            '<th class="s">Size</th><th class="t">Type</th></tr></thead>'
        )
        html_parts.append("<tbody>")

        for name in entries:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            filetype = "File"
            lastmodified = "-"
            filesize = ""

            # Determine file type and metadata
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
                filetype = "Directory"
            elif os.path.islink(fullname):
                displayname = name + "@"
                filetype = "Link"
            elif os.path.isfile(fullname):
                try:
                    statdict = os.stat(fullname)
                    lastmodified = datetime.datetime.fromtimestamp(statdict.st_mtime)
                    filesize = self._human_readable_size(
                        statdict.st_size, decimal_places=2
                    )
                except OSError:
                    pass

            # Build the current path for the link
            if display_path.endswith("/"):
                link_path = display_path + urllib.parse.quote(
                    linkname, errors="surrogatepass"
                )
            else:
                link_path = (
                    display_path
                    + "/"
                    + urllib.parse.quote(linkname, errors="surrogatepass")
                )

            html_parts.append(
                "<tr>"
                f'<td class="n"><a href="{link_path}">{html.escape(displayname, quote=False)}</a></td>'
                f'<td class="m">{lastmodified}</td>'
                f'<td class="s">{filesize}</td>'
                f'<td class="t">{filetype}</td>'
                "</tr>"
            )

        html_parts.append("</tbody>")
        html_parts.append("</table>")
        html_parts.append("</div></body>\n</html>\n")

        return "\n".join(html_parts)

    def _setup_routes(self):
        """Setup FastAPI routes with access to SimStackServer"""

        @self.app.get("/", tags=["Server"])
        async def root():
            """Service identity and API version.

            Use this endpoint to verify the server is reachable and to
            discover the API version before making further calls.
            """
            return {
                "status": "running",
                "service": "SimStackServer",
                "api_version": "1.0.0",
            }

        @self.app.get("/health", tags=["Server"])
        async def health_check():
            """Server health check.

            Returns the current number of running workflows.  Useful as a
            liveness probe or pre-flight check before submitting work.
            """
            return {
                "status": "healthy",
                "workflows_running": self.simstack_server._workflow_manager.workflows_running(),
            }

        # ==================== HTTP Server Routes (Directory Browsing) ====================

        @self.app.get(
            "/http/static/{filename}", tags=["Browse"], include_in_schema=False
        )
        async def serve_static_file(filename: str):
            """Serve static files (favicon.ico, dirlist.css)"""
            try:
                static_path = self._get_static_http_path()
                file_path = os.path.join(static_path, filename)

                # Security check: ensure file is within static directory
                if not os.path.abspath(file_path).startswith(
                    os.path.abspath(static_path)
                ):
                    raise HTTPException(status_code=403, detail="Access denied")

                if not os.path.exists(file_path):
                    self._logger.warning(f"Static file not found: {file_path}")
                    raise HTTPException(status_code=404, detail="File not found")

                if not os.path.isfile(file_path):
                    raise HTTPException(status_code=400, detail="Not a file")

                # Determine MIME type
                mime_type = self._guess_mime_type(filename)

                self._logger.info(
                    f"Serving static file: {file_path} ({os.path.getsize(file_path)} bytes)"
                )
                return FileResponse(file_path, media_type=mime_type)
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error serving static file: {filename}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/http/browse", tags=["Browse"])
        async def browse_root():
            """Interactive HTML directory browser (root).

            Opens the basepath directory in a web-browser-friendly HTML listing.
            Useful for quick manual inspection of workflow results.
            """
            base_dir = self._get_http_base_directory()
            return HTMLResponse(
                content=self._generate_directory_listing_html(base_dir, "/http/browse/")
            )

        @self.app.get("/http/browse/{path:path}", tags=["Browse"])
        async def browse_directory(path: str):
            """Interactive HTML directory browser (navigate into sub-paths).

            If the path points to a directory, an HTML listing is returned.
            If it points to a file, the file content is returned directly
            (with an appropriate MIME type).
            """
            try:
                base_dir = self._get_http_base_directory()

                # Decode URL path
                try:
                    decoded_path = urllib.parse.unquote(path, errors="surrogatepass")
                except UnicodeDecodeError:
                    decoded_path = urllib.parse.unquote(path)

                # Build full path
                full_path = os.path.join(base_dir, decoded_path)

                # Security check: ensure path is within base directory
                if not os.path.abspath(full_path).startswith(os.path.abspath(base_dir)):
                    raise HTTPException(status_code=403, detail="Access denied")

                if not os.path.exists(full_path):
                    self._logger.warning(f"Browse path not found: {full_path}")
                    raise HTTPException(status_code=404, detail="Path not found")

                # If it's a directory, show listing
                if os.path.isdir(full_path):
                    html_content = self._generate_directory_listing_html(
                        full_path, f"/http/browse/{path}"
                    )
                    return HTMLResponse(content=html_content)

                # If it's a file, serve it
                elif os.path.isfile(full_path):
                    mime_type = self._guess_mime_type(full_path)
                    self._logger.info(
                        f"Serving browse file: {full_path} ({os.path.getsize(full_path)} bytes)"
                    )
                    return FileResponse(full_path, media_type=mime_type)

                else:
                    raise HTTPException(
                        status_code=400, detail="Not a file or directory"
                    )

            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error browsing path: {path}")
                raise HTTPException(status_code=500, detail=str(e))

        # ==================== API Routes ====================

        @self.app.get("/api/workflows", tags=["Workflows"])
        async def list_workflows():
            """List all workflows grouped by state.

            Returns both in-progress and finished workflows in a single call.
            Each workflow entry contains `id` (the submit name), `name`, and
            `path` (storage directory relative to basepath).
            """
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

        @self.app.get("/api/workflows/inprogress", tags=["Workflows"])
        async def list_inprogress_workflows():
            """List workflows that are currently executing.

            Poll this endpoint (together with `/api/workflows/finished`) to
            detect when a submitted workflow completes.  Each entry contains
            `id` (the submit name used to identify the workflow) and `name`.
            """
            try:
                workflows = (
                    self.simstack_server._workflow_manager.get_inprogress_workflows()
                )
                return {"workflows": workflows, "count": len(workflows)}
            except Exception as e:
                self._logger.exception("Error listing in-progress workflows")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/workflows/finished", tags=["Workflows"])
        async def list_finished_workflows():
            """List workflows that have completed (successfully or with errors).

            A workflow moves here once all its steps finish or if it is
            aborted.  Match on the `name` field to detect completion of a
            specific submission.
            """
            try:
                workflows = (
                    self.simstack_server._workflow_manager.get_finished_workflows()
                )
                return {"workflows": workflows, "count": len(workflows)}
            except Exception as e:
                self._logger.exception("Error listing finished workflows")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/workflows/{workflow_id}/jobs", tags=["Workflows"])
        async def list_workflow_jobs(workflow_id: str):
            """List the individual jobs (WFEMs) inside a workflow.

            `workflow_id` is the submit name returned when the workflow was
            submitted (e.g. `demo_dsl_wf_2024-01-01-12h00m00s`).
            """
            try:
                jobs = self.simstack_server._workflow_manager.list_jobs_of_workflow(
                    workflow_id
                )
                return {"workflow_id": workflow_id, "jobs": jobs, "count": len(jobs)}
            except Exception as e:
                self._logger.exception(f"Error listing jobs for workflow {workflow_id}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/workflows/{workflow_id}/abort", tags=["Workflows"])
        async def abort_workflow(workflow_id: str):
            """Request cancellation of a running workflow.

            All pending jobs are cancelled.  Already-finished jobs are not
            affected.  The workflow moves to the finished list with an
            aborted status.
            """
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

        @self.app.delete("/api/workflows/{workflow_id}", tags=["Workflows"])
        async def delete_workflow(workflow_id: str):
            """Delete a workflow and its storage directory.

            Removes the workflow from the server's internal tracking and
            deletes the associated files under the basepath.  Only call this
            after you have retrieved any results you need.
            """
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

        @self.app.get("/api/singlejobs/{job_uid}/status", tags=["Single Jobs"])
        async def get_singlejob_status(job_uid: str):
            """Poll the execution status of a single job.

            Returns `{"job_uid": "...", "status": {"status": "inprogress"}}` while
            the job is running, and `{"job_uid": "...", "status": {"status": "finished"}}`
            once it completes.  Poll this endpoint at a reasonable interval
            (e.g. every 2 s) after submission.

            Output files are available under `singlejobs/{job_uid}/` once the
            job finishes — use `/api/files/list` to enumerate them.
            """
            try:
                status = self.simstack_server._workflow_manager.get_singlejob_status(
                    job_uid
                )
                return {"job_uid": job_uid, "status": status}
            except Exception as e:
                self._logger.exception(f"Error getting status for job {job_uid}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/singlejobs/{job_uid}/abort", tags=["Single Jobs"])
        async def abort_singlejob(job_uid: str):
            """Request cancellation of a running single job."""
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

        @self.app.post(
            "/api/workflows/submit",
            response_model=SubmitWorkflowResponse,
            tags=["Workflows"],
        )
        async def submit_workflow(request: SubmitWorkflowRequest):
            """Submit a previously uploaded workflow for execution.

            Before calling this endpoint you must upload the full workflow tree:

            1. Upload all files under `workflow_data/<StepName>/inputs/…` via
               `/api/files/upload` with `to_file` set to the relative path.
            2. Upload `rendered_workflow.xml` to `<workflow_name>/rendered_workflow.xml`.
            3. Call this endpoint with `filename` pointing to that XML file.

            The server reads the XML, resolves all step dependencies, and begins
            executing the DAG.  Poll `/api/workflows/inprogress` and
            `/api/workflows/finished` to track progress.
            """
            try:
                workflow_filename = self._resolve_path(request.filename)

                self._logger.info(f"Workflow submission requested: {workflow_filename}")

                # Add to submission queue
                self.simstack_server._submitted_workflow_queue.put(workflow_filename)

                return SubmitWorkflowResponse(
                    status="submitted",
                    message="Workflow has been submitted for execution",
                    filename=request.filename,
                )
            except Exception as e:
                self._logger.exception(f"Error submitting workflow: {request.filename}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post(
            "/api/singlejobs/submit",
            response_model=SubmitSingleJobResponse,
            tags=["Single Jobs"],
        )
        async def submit_singlejob(request: SubmitSingleJobRequest):
            """Submit a self-contained single job for execution.

            The request body must contain a serialised WFEM dict (see
            `SubmitSingleJobRequest`).  The server unpacks the embedded WaNo
            bundle, renders the WaNo parameters, and executes the job script.

            If the WaNo has external input files (e.g. `<WaNoFile>` parameters),
            upload them via `/api/files/upload` **before** calling this endpoint.
            The WFEM's stage-in list tells the server where to find each file
            relative to the basepath.

            Returns a `job_uid` that you use with
            `GET /api/singlejobs/{job_uid}/status` to poll for completion.
            """
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
                    job_uid=wfem.uid,
                )
            except Exception as e:
                self._logger.exception("Error submitting single job")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post(
            "/api/wano/required-files",
            response_model=WanoRequiredFilesResponse,
            tags=["WaNo Introspection"],
        )
        async def wano_required_files(request: WanoRequiredFilesRequest):
            """Discover which external files a WaNo requires before execution.

            POST a `wano_spec` dict (produced client-side by
            `WaNoModelRoot.to_spec()`) and receive back the list of
            user-supplied files that must be uploaded before the job can run.
            Files that are part of the WaNo definition itself (XML, scripts)
            are **not** listed here — only files the user must provide.
            """
            try:
                from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

                wmr = WaNoModelRoot.from_spec(request.wano_spec)
                external_files = wmr.get_external_input_files()
                return WanoRequiredFilesResponse(
                    wano_name=wmr.name,
                    external_input_files=[
                        ExternalInputFileInfo(logical_name=lname, source_path=src)
                        for lname, src in external_files
                    ],
                )
            except Exception as e:
                self._logger.exception("Error resolving required files for WaNo")
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post(
            "/api/workflows/required-files",
            response_model=WorkflowRequiredFilesResponse,
            tags=["WaNo Introspection"],
        )
        async def workflow_required_files(request: WorkflowRequiredFilesRequest):
            """Build an upload manifest for a complete multi-step workflow.

            POST a list of `{wano_spec, wfem_path}` objects — one per WaNo node
            in the workflow DAG.  The response categorises every file into:

            - **wano_definition** — generated by the submission pipeline (XML,
              scripts, config files).  These are uploaded automatically.
            - **external_input** — scientific data files the **user** must supply.

            The `required_user_uploads` field is the filtered list of
            external-input items — this is what the client should present to
            the user as "files you need to provide".
            """
            try:
                from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
                from SimStackServer.WaNo.upload_manifest import WorkflowUploadManifest

                manifest = WorkflowUploadManifest()
                for node in request.nodes:
                    wmr = WaNoModelRoot.from_spec(node.wano_spec)
                    manifest.add_wano(wmr, node.wfem_path)

                def _to_response(items):
                    return [
                        UploadItemResponse(
                            server_path=i.server_path,
                            logical_name=i.logical_name,
                            wfem_name=i.wfem_name,
                            wfem_path=i.wfem_path,
                            category=i.category,
                            local_source=i.local_source,
                            required=i.required,
                        )
                        for i in items
                    ]

                return WorkflowRequiredFilesResponse(
                    all_items=_to_response(manifest.all_items()),
                    required_user_uploads=_to_response(
                        manifest.required_user_uploads()
                    ),
                    wano_definition_items=_to_response(
                        manifest.wano_definition_items()
                    ),
                    summary=manifest.summary(),
                )
            except Exception as e:
                self._logger.exception("Error building workflow upload manifest")
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post(
            "/api/server/shutdown", response_model=ShutdownResponse, tags=["Server"]
        )
        async def shutdown_server():
            """Initiate a graceful server shutdown."""
            try:
                self._logger.info("Server shutdown requested via API")
                self.simstack_server._stop_main = True
                self.simstack_server._stop_thread = True

                return ShutdownResponse(
                    status="shutting_down", message="Server shutdown has been initiated"
                )
            except Exception as e:
                self._logger.exception("Error during server shutdown")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/server/clear-state", tags=["Server"])
        async def clear_server_state():
            """Clear all in-memory server state (for testing).

            Removes all tracked workflows and single jobs from the server's
            internal state.  Does **not** delete files on disk.
            """
            try:
                self._logger.info("Hard clearing server state via API")
                self.simstack_server._clear_server_state()

                return {"status": "cleared", "message": "Server state has been cleared"}
            except Exception as e:
                self._logger.exception("Error clearing server state")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post(
            "/api/configure", response_model=ConfigureResponse, tags=["Server"]
        )
        async def configure(request: ConfigureRequest):
            """Update the server's compute-resource configuration.

            Accepts a serialised `Resources` dict (queueing system, walltime,
            CPUs, memory, etc.) and persists it to the server's config file.
            """
            try:
                # Create Resources object from dict
                resources = Resources()
                resources.from_dict(request.resources)

                # Update the ServerConfig with the new resources
                server_config = Config.get_server_config()
                if server_config is None:
                    raise HTTPException(
                        status_code=500,
                        detail="ServerConfig not initialized. Server must be started first.",
                    )
                server_config.resources = resources
                config_path = Config.save_server_config(server_config)

                return ConfigureResponse(
                    status="configured",
                    message=f"Resources configuration saved to {config_path}",
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception("Error configuring resources")
                raise HTTPException(status_code=500, detail=str(e))

        # File Operations API

        @self.app.post(
            "/api/files/exists", response_model=ExistsResponse, tags=["Files"]
        )
        async def check_file_exists(request: FilePathRequest):
            """Check whether a file or directory exists on the server.

            The `filename` is resolved relative to the server basepath
            (default `~/simstack_workspace`).
            """
            try:
                filepath = self._resolve_path(
                    request.filename, request.basepath_override
                )
                exists = os.path.exists(filepath)
                is_dir = os.path.isdir(filepath) if exists else None
                return ExistsResponse(
                    exists=exists, path=request.filename, is_directory=is_dir
                )
            except Exception as e:
                self._logger.exception(
                    f"Error checking if file exists: {request.filename}"
                )
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post(
            "/api/files/list", response_model=ListDirResponse, tags=["Files"]
        )
        async def list_directory(request: ListDirRequest):
            """List the contents of a directory on the server.

            The `path` is resolved relative to the server basepath.  Each entry
            in the response has a `type` field: `"d"` for directories, `"f"` for
            files.

            **Common paths to list:**

            - `singlejobs/{job_uid}/` — output files of a single job.
            - `<workflow_name>/` — top-level workflow directory (contains
              `exec_directories/`, `workflow_data/`, `rendered_workflow.xml`).
            - `<workflow_name>/workflow_data/<StepName>/outputs/` — output files
              of a specific workflow step.
            """
            try:
                dirpath = self._resolve_path(request.path, request.basepath_override)

                if not os.path.exists(dirpath):
                    self._logger.warning(f"Directory not found: {dirpath}")
                    raise HTTPException(
                        status_code=404, detail=f"Directory not found: {request.path}"
                    )

                if not os.path.isdir(dirpath):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path is not a directory: {request.path}",
                    )

                files = []
                for entry in os.listdir(dirpath):
                    entry_path = os.path.join(dirpath, entry)
                    file_type = "d" if os.path.isdir(entry_path) else "f"
                    files.append(FileInfo(name=entry, path=dirpath, type=file_type))

                return ListDirResponse(files=files, count=len(files))
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error listing directory: {request.path}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/files/mkdir", response_model=MkdirResponse, tags=["Files"])
        async def create_directory(request: MkdirRequest):
            """Create a directory on the server (recursively).

            The path is resolved relative to the server basepath.  Parent
            directories are created automatically.  Returns `created: false` if
            the directory already exists (not an error).
            """
            try:
                dirpath = self._resolve_path(
                    request.directory, request.basepath_override
                )

                if os.path.exists(dirpath):
                    if not os.path.isdir(dirpath):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Path exists but is not a directory: {request.directory}",
                        )
                    return MkdirResponse(
                        created=False, path=request.directory, absolute_path=dirpath
                    )

                os.makedirs(dirpath, mode=request.mode_override or 0o770, exist_ok=True)
                self._logger.info(f"Created directory: {dirpath}")

                return MkdirResponse(
                    created=True, path=request.directory, absolute_path=dirpath
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error creating directory: {request.directory}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete(
            "/api/files/delete", response_model=DeleteResponse, tags=["Files"]
        )
        async def delete_file(request: FilePathRequest):
            """Delete a single file.  Use `/api/files/rmtree` for directories."""
            try:
                filepath = self._resolve_path(
                    request.filename, request.basepath_override
                )

                if not os.path.exists(filepath):
                    self._logger.warning(f"File not found for deletion: {filepath}")
                    raise HTTPException(
                        status_code=404, detail=f"File not found: {request.filename}"
                    )

                if os.path.isdir(filepath):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path is a directory, use /api/files/rmtree instead: {request.filename}",
                    )

                os.remove(filepath)
                self._logger.info(f"Deleted file: {filepath}")

                return DeleteResponse(
                    deleted=True,
                    path=request.filename,
                    message="File deleted successfully",
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error deleting file: {request.filename}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete(
            "/api/files/rmtree", response_model=DeleteResponse, tags=["Files"]
        )
        async def remove_directory_tree(request: DirectoryPathRequest):
            """Recursively delete a directory and all its contents.

            Safety checks prevent deletion of paths outside the basepath or
            too close to the home directory.
            """
            try:
                # --- Safety gate 1: basepath must be explicitly configured ---
                if request.basepath_override in [None, ""]:
                    resources = Config.get_resources()
                    effective_basepath = resources.basepath if resources else None
                else:
                    effective_basepath = request.basepath_override

                if not effective_basepath:
                    self._logger.warning(
                        f"rmtree refused for {request.dirname!r}: basepath is not configured"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="rmtree refused: basepath is not configured",
                    )

                dirpath = self._resolve_path(request.dirname, request.basepath_override)

                # Resolve symlinks / '..' before any comparison
                home_dir = Path.home().resolve()
                dirpath_abs = Path(dirpath).resolve()

                abs_basepath = Path(effective_basepath)
                if not abs_basepath.is_absolute():
                    abs_basepath = home_dir / abs_basepath
                abs_basepath = abs_basepath.resolve()

                # --- Safety gate 2: target must be inside basepath ---
                try:
                    dirpath_abs.relative_to(abs_basepath)
                except ValueError:
                    self._logger.warning(
                        f"rmtree refused: {dirpath_abs} is not within basepath {abs_basepath}"
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="rmtree refused: path is not within basepath",
                    )

                # --- Safety gate 3: must be >= 2 levels below home ---
                try:
                    rel_parts = dirpath_abs.relative_to(home_dir).parts
                    if len(rel_parts) < 2:
                        self._logger.warning(
                            f"rmtree refused: {dirpath_abs} is too close to home directory"
                        )
                        raise HTTPException(
                            status_code=403,
                            detail="rmtree refused: path must be at least 2 levels below home directory",
                        )
                except ValueError:
                    pass  # Not under home at all — no proximity concern

                if not os.path.exists(dirpath):
                    # Silently succeed if directory doesn't exist (like ClusterManager.rmtree)
                    return DeleteResponse(
                        deleted=False,
                        path=request.dirname,
                        message="Directory does not exist",
                    )

                if not os.path.isdir(dirpath):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Path is not a directory: {request.dirname}",
                    )

                import shutil

                shutil.rmtree(dirpath)
                self._logger.info(f"Deleted directory tree: {dirpath}")

                return DeleteResponse(
                    deleted=True,
                    path=request.dirname,
                    message="Directory deleted successfully",
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error deleting directory: {request.dirname}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/files/upload", tags=["Files"])
        async def upload_file(
            file: UploadFile = File(
                ..., description="The file to upload (multipart form)."
            ),
            to_file: Optional[str] = Form(
                None,
                description=(
                    "Destination path **relative to the server basepath**.  "
                    "Parent directories are created automatically.  "
                    "If omitted, the original filename from the upload is used.  "
                    "Example: `my_workflow/workflow_data/Step1/inputs/config.xml`"
                ),
            ),
            basepath_override: Optional[str] = Form(
                None, description="Override the default basepath (advanced)."
            ),
        ):
            """Upload a file to the server.

            This is the primary mechanism for staging workflow data before
            submission.  Use the `to_file` form field to control where the file
            lands relative to the basepath.

            **Example with curl:**

            ```bash
            curl -X POST https://localhost:8080/api/files/upload \\
              -u user:pass \\
              -F 'file=@local_data.csv' \\
              -F 'to_file=my_workflow/workflow_data/Step1/inputs/data.csv'
            ```

            **Example with Python requests:**

            ```python
            requests.post(
                "https://localhost:8080/api/files/upload",
                auth=("user", "pass"),
                files={"file": ("data.csv", open("local_data.csv", "rb"))},
                data={"to_file": "my_workflow/workflow_data/Step1/inputs/data.csv"},
            )
            ```
            """
            try:
                # Use the provided path or fall back to the original filename
                destination = to_file if to_file else file.filename

                filepath = self._resolve_path(destination, basepath_override)

                # If to_file resolves to an existing directory, or the path ends
                # with '/', place the file inside that directory using the
                # original upload filename.
                if os.path.isdir(filepath) or (
                    destination and destination.endswith("/")
                ):
                    original_name = os.path.basename(file.filename or "")
                    if not original_name:
                        raise HTTPException(
                            status_code=400,
                            detail="to_file is a directory but the upload carries no filename",
                        )
                    filepath = os.path.join(filepath, original_name)
                    destination = os.path.join(destination.rstrip("/"), original_name)
                    self._logger.info(f"to_file is a directory; writing to {filepath}")

                # Create directory if it doesn't exist
                dir_path = os.path.dirname(filepath)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)

                # Write file
                with open(filepath, "wb") as f:
                    content = await file.read()
                    f.write(content)

                self._logger.info(f"Uploaded file: {filepath} ({len(content)} bytes)")

                return FileOperationResponse(
                    success=True, message="File uploaded successfully", path=destination
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error uploading file to: {to_file}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/files/download", tags=["Files"])
        async def download_file(
            from_file: str = Query(
                ..., description="Path to download, relative to basepath."
            ),
            basepath_override: Optional[str] = Query(
                None, description="Override the default basepath (advanced)."
            ),
        ):
            """Download a file from the server.

            Returns the raw file content as `application/octet-stream`.
            The `from_file` path is resolved relative to the server basepath.

            **Example:** To retrieve a job's output after completion:

            ```
            GET /api/files/download?from_file=singlejobs/{job_uid}/output_dict.yml
            ```
            """
            try:
                filepath = self._resolve_path(from_file, basepath_override)

                if not os.path.exists(filepath):
                    self._logger.warning(f"File not found for download: {filepath}")
                    raise HTTPException(
                        status_code=404, detail=f"File not found: {from_file}"
                    )

                if os.path.isdir(filepath):
                    raise HTTPException(
                        status_code=400, detail=f"Path is a directory: {from_file}"
                    )

                self._logger.info(
                    f"Serving file download: {filepath} ({os.path.getsize(filepath)} bytes)"
                )
                return FileResponse(
                    filepath,
                    filename=os.path.basename(filepath),
                    media_type="application/octet-stream",
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error downloading file: {from_file}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/files/put", tags=["Files"])
        async def put_file_content(
            content: UploadFile = File(..., description="File content to write."),
            to_file: str = Form(
                ..., description="Destination path relative to basepath."
            ),
            basepath_override: Optional[str] = Form(
                None, description="Override the default basepath (advanced)."
            ),
        ):
            """Write content directly to a file on the server.

            Similar to `/api/files/upload` but uses `content` as the form
            field name.  Functionally equivalent — prefer `/api/files/upload`
            for new clients.
            """
            try:
                filepath = self._resolve_path(to_file, basepath_override)

                # Create directory if it doesn't exist
                dir_path = os.path.dirname(filepath)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)

                # Read and write content to file
                file_content = await content.read()
                with open(filepath, "wb") as f:
                    f.write(file_content)

                self._logger.info(
                    f"Wrote content to file: {filepath} ({len(file_content)} bytes)"
                )

                return FileOperationResponse(
                    success=True,
                    message="File content written successfully",
                    path=to_file,
                )
            except HTTPException:
                raise
            except Exception as e:
                self._logger.exception(f"Error writing content to file: {to_file}")
                raise HTTPException(status_code=500, detail=str(e))

    def _get_http_base_directory(self) -> str:
        """
        Return the base directory used for HTTP browsing.

        Uses the explicitly set _http_base_directory when available, otherwise
        falls back to the configured basepath (same resolution logic as
        _resolve_path: relative paths are anchored to the user home directory).
        """
        basepath = Config.get_resources().basepath
        if basepath and not os.path.isabs(basepath):
            basepath = os.path.join(str(Path.home()), basepath)
        return basepath

    def _resolve_path(self, path: str, basepath_override: Optional[str] = None) -> str:
        """Resolve a client-supplied path to an absolute filesystem path.

        Every path accepted by the API (file uploads, downloads, directory
        listings, workflow filenames) passes through this method.  The
        algorithm is:

        1. Strip any leading ``/`` from *path*.
        2. Determine the basepath: use *basepath_override* if provided,
           otherwise the server's configured ``resources.basepath``
           (default ``simstack_workspace``).
        3. If the basepath is relative, prepend the user's home directory.
        4. Return ``os.path.join(basepath, path)``.

        This means clients should always send paths **relative to the
        basepath** (e.g. ``my_workflow/rendered_workflow.xml``), never
        absolute filesystem paths.
        """
        if basepath_override in [None, ""]:
            basepath = Config.get_resources().basepath
        else:
            basepath = basepath_override

        # Remove leading slash if present
        if path.startswith("/"):
            path = path[1:]
        # If basepath is relative, resolve in HOME:
        if not os.path.isabs(basepath):
            home_dir = str(Path.home())
            basepath = os.path.join(home_dir, basepath)

        return os.path.join(basepath, path)

    def run(self):
        """Run the uvicorn server"""
        config_args = {
            "app": self.app,
            "host": self.host,
            "port": self.port,
            "log_level": "info",
            "access_log": False,  # Use existing logging system
        }

        # Add SSL configuration if HTTPS is enabled
        if self.use_https and self.ssl_keyfile and self.ssl_certfile:
            config_args["ssl_keyfile"] = self.ssl_keyfile
            config_args["ssl_certfile"] = self.ssl_certfile

        config = uvicorn.Config(**config_args)
        self.server = uvicorn.Server(config)

        protocol = "https" if self.use_https else "http"
        self._logger.info(
            f"Starting FastAPI server on {protocol}://{self.host}:{self.port}"
        )
        if self.use_https:
            self._logger.info(
                f"Using self-signed certificates - SSL cert: {self.ssl_certfile}"
            )

        self.server.run()

    def shutdown(self):
        """Gracefully shutdown the server"""
        if self.server:
            self._logger.info("Shutting down FastAPI server")
            self.server.should_exit = True
