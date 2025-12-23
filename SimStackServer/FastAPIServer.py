import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI, HTTPException

if TYPE_CHECKING:
    from SimStackServer.SimStackServerMain import SimStackServer


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
