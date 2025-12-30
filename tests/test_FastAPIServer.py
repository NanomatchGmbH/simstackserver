import pytest
import time
import tempfile
import os
import shutil
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from io import BytesIO

from SimStackServer.FastAPIServer import FastAPIThread


@pytest.fixture
def mock_workflow_manager():
    """Create a mock WorkflowManager with common methods"""
    wfm = Mock()
    wfm.workflows_running.return_value = 2
    wfm.get_inprogress_workflows.return_value = [
        {
            "id": "wf1",
            "name": "workflow1",
            "path": "/path/to/wf1",
            "status": "running",
            "type": "w",
        },
        {
            "id": "wf2",
            "name": "workflow2",
            "path": "/path/to/wf2",
            "status": "running",
            "type": "w",
        },
    ]
    wfm.get_finished_workflows.return_value = [
        {
            "id": "wf3",
            "name": "workflow3",
            "path": "/path/to/wf3",
            "status": "finished",
            "type": "w",
        }
    ]
    wfm.list_jobs_of_workflow.return_value = [
        {"job_id": "job1", "status": "running"},
        {"job_id": "job2", "status": "completed"},
    ]
    wfm.get_singlejob_status.return_value = {"status": "inprogress"}
    return wfm


@pytest.fixture
def mock_simstack_server(mock_workflow_manager):
    """Create a mock SimStackServer"""
    server = Mock()
    server._workflow_manager = mock_workflow_manager
    return server


@pytest.fixture
def fastapi_thread(mock_simstack_server):
    """Create a FastAPIThread instance with mock server"""
    thread = FastAPIThread(mock_simstack_server, host="127.0.0.1", port=8001)
    return thread


@pytest.fixture
def test_client(fastapi_thread):
    """Create a FastAPI TestClient for testing endpoints"""
    return TestClient(fastapi_thread.app)


# ==================== Endpoint Tests ====================


def test_root_endpoint(test_client):
    """Test the root endpoint returns service information"""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["service"] == "SimStackServer"
    assert data["api_version"] == "1.0.0"


def test_health_check_endpoint(test_client, mock_workflow_manager):
    """Test the health check endpoint"""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["workflows_running"] == 2
    mock_workflow_manager.workflows_running.assert_called_once()


def test_list_all_workflows(test_client, mock_workflow_manager):
    """Test listing all workflows (in-progress and finished)"""
    response = test_client.get("/api/workflows")
    assert response.status_code == 200
    data = response.json()
    assert "inprogress" in data
    assert "finished" in data
    assert "total" in data
    assert len(data["inprogress"]) == 2
    assert len(data["finished"]) == 1
    assert data["total"] == 3
    mock_workflow_manager.get_inprogress_workflows.assert_called_once()
    mock_workflow_manager.get_finished_workflows.assert_called_once()


def test_list_inprogress_workflows(test_client, mock_workflow_manager):
    """Test listing in-progress workflows only"""
    response = test_client.get("/api/workflows/inprogress")
    assert response.status_code == 200
    data = response.json()
    assert "workflows" in data
    assert "count" in data
    assert len(data["workflows"]) == 2
    assert data["count"] == 2
    assert data["workflows"][0]["id"] == "wf1"
    mock_workflow_manager.get_inprogress_workflows.assert_called_once()


def test_list_finished_workflows(test_client, mock_workflow_manager):
    """Test listing finished workflows only"""
    response = test_client.get("/api/workflows/finished")
    assert response.status_code == 200
    data = response.json()
    assert "workflows" in data
    assert "count" in data
    assert len(data["workflows"]) == 1
    assert data["count"] == 1
    assert data["workflows"][0]["id"] == "wf3"
    mock_workflow_manager.get_finished_workflows.assert_called_once()


def test_list_workflow_jobs(test_client, mock_workflow_manager):
    """Test listing jobs for a specific workflow"""
    response = test_client.get("/api/workflows/wf1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == "wf1"
    assert "jobs" in data
    assert "count" in data
    assert len(data["jobs"]) == 2
    assert data["count"] == 2
    mock_workflow_manager.list_jobs_of_workflow.assert_called_once_with("wf1")


def test_abort_workflow(test_client, mock_workflow_manager):
    """Test aborting a workflow"""
    response = test_client.post("/api/workflows/wf1/abort")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "abort_requested"
    assert data["workflow_id"] == "wf1"
    assert "message" in data
    mock_workflow_manager.abort_workflow.assert_called_once_with("wf1")


def test_delete_workflow(test_client, mock_workflow_manager):
    """Test deleting a workflow"""
    response = test_client.delete("/api/workflows/wf1")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert data["workflow_id"] == "wf1"
    assert "message" in data
    mock_workflow_manager.delete_workflow.assert_called_once_with("wf1")


def test_get_singlejob_status(test_client, mock_workflow_manager):
    """Test getting status of a single job"""
    response = test_client.get("/api/singlejobs/job123/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_uid"] == "job123"
    assert "status" in data
    assert data["status"]["status"] == "inprogress"
    mock_workflow_manager.get_singlejob_status.assert_called_once_with("job123")


def test_abort_singlejob(test_client, mock_workflow_manager):
    """Test aborting a single job"""
    response = test_client.post("/api/singlejobs/job123/abort")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "abort_requested"
    assert data["job_uid"] == "job123"
    assert "message" in data
    mock_workflow_manager.abort_singlejob.assert_called_once_with("job123")


# ==================== Error Handling Tests ====================


def test_list_workflows_error(test_client, mock_workflow_manager):
    """Test error handling when listing workflows fails"""
    mock_workflow_manager.get_inprogress_workflows.side_effect = Exception(
        "Database error"
    )
    response = test_client.get("/api/workflows")
    assert response.status_code == 500
    assert "Database error" in response.json()["detail"]


def test_list_inprogress_workflows_error(test_client, mock_workflow_manager):
    """Test error handling when listing in-progress workflows fails"""
    mock_workflow_manager.get_inprogress_workflows.side_effect = RuntimeError(
        "Connection failed"
    )
    response = test_client.get("/api/workflows/inprogress")
    assert response.status_code == 500
    assert "Connection failed" in response.json()["detail"]


def test_list_finished_workflows_error(test_client, mock_workflow_manager):
    """Test error handling when listing finished workflows fails"""
    mock_workflow_manager.get_finished_workflows.side_effect = Exception("IO error")
    response = test_client.get("/api/workflows/finished")
    assert response.status_code == 500
    assert "IO error" in response.json()["detail"]


def test_list_workflow_jobs_error(test_client, mock_workflow_manager):
    """Test error handling when listing workflow jobs fails"""
    mock_workflow_manager.list_jobs_of_workflow.side_effect = Exception(
        "Workflow not found"
    )
    response = test_client.get("/api/workflows/nonexistent/jobs")
    assert response.status_code == 500
    assert "Workflow not found" in response.json()["detail"]


def test_abort_workflow_error(test_client, mock_workflow_manager):
    """Test error handling when aborting workflow fails"""
    mock_workflow_manager.abort_workflow.side_effect = Exception("Abort failed")
    response = test_client.post("/api/workflows/wf1/abort")
    assert response.status_code == 500
    assert "Abort failed" in response.json()["detail"]


def test_delete_workflow_error(test_client, mock_workflow_manager):
    """Test error handling when deleting workflow fails"""
    mock_workflow_manager.delete_workflow.side_effect = Exception("Delete failed")
    response = test_client.delete("/api/workflows/wf1")
    assert response.status_code == 500
    assert "Delete failed" in response.json()["detail"]


def test_get_singlejob_status_error(test_client, mock_workflow_manager):
    """Test error handling when getting single job status fails"""
    mock_workflow_manager.get_singlejob_status.side_effect = Exception("Job not found")
    response = test_client.get("/api/singlejobs/job123/status")
    assert response.status_code == 500
    assert "Job not found" in response.json()["detail"]


def test_abort_singlejob_error(test_client, mock_workflow_manager):
    """Test error handling when aborting single job fails"""
    mock_workflow_manager.abort_singlejob.side_effect = Exception("Cannot abort job")
    response = test_client.post("/api/singlejobs/job123/abort")
    assert response.status_code == 500
    assert "Cannot abort job" in response.json()["detail"]


# ==================== Thread Lifecycle Tests ====================


def test_fastapi_thread_initialization(fastapi_thread, mock_simstack_server):
    """Test FastAPIThread initialization"""
    assert fastapi_thread.simstack_server == mock_simstack_server
    assert fastapi_thread.host == "127.0.0.1"
    assert fastapi_thread.port == 8001
    assert fastapi_thread.server is None
    assert fastapi_thread.app is not None
    assert fastapi_thread.daemon is True
    assert fastapi_thread.name == "FastAPI-Thread"


def test_fastapi_thread_run_method_starts_server(mock_simstack_server):
    """Test that run method starts the uvicorn server"""
    with patch("SimStackServer.FastAPIServer.uvicorn.Server") as mock_uvicorn_server:
        mock_server_instance = Mock()
        mock_uvicorn_server.return_value = mock_server_instance

        thread = FastAPIThread(mock_simstack_server, host="127.0.0.1", port=8002)

        # Start the thread in the background
        thread.start()
        time.sleep(0.2)  # Give it a moment to start

        # Verify uvicorn Server was created
        mock_uvicorn_server.assert_called_once()

        # Verify server.run was called
        mock_server_instance.run.assert_called_once()


def test_fastapi_thread_shutdown(mock_simstack_server):
    """Test FastAPIThread shutdown method"""
    thread = FastAPIThread(mock_simstack_server, host="127.0.0.1", port=8003)

    # Create a mock server
    mock_server = Mock()
    thread.server = mock_server

    # Call shutdown
    thread.shutdown()

    # Verify should_exit was set to True
    assert mock_server.should_exit is True


def test_fastapi_thread_shutdown_without_server(mock_simstack_server):
    """Test FastAPIThread shutdown when server is None"""
    thread = FastAPIThread(mock_simstack_server, host="127.0.0.1", port=8004)

    # Server is None by default
    assert thread.server is None

    # Should not raise exception
    thread.shutdown()


# ==================== Integration Tests ====================


def test_workflow_manager_called_correctly(test_client, mock_workflow_manager):
    """Test that workflow manager methods are called with correct parameters"""
    # Test multiple endpoints to ensure proper integration
    test_client.get("/api/workflows")
    test_client.get("/api/workflows/inprogress")
    test_client.get("/api/workflows/finished")
    test_client.get("/api/workflows/my-workflow/jobs")
    test_client.post("/api/workflows/my-workflow/abort")
    test_client.delete("/api/workflows/my-workflow")
    test_client.get("/api/singlejobs/my-job/status")
    test_client.post("/api/singlejobs/my-job/abort")

    # Verify all calls were made
    assert mock_workflow_manager.get_inprogress_workflows.call_count == 2
    assert mock_workflow_manager.get_finished_workflows.call_count == 2
    mock_workflow_manager.list_jobs_of_workflow.assert_called_with("my-workflow")
    mock_workflow_manager.abort_workflow.assert_called_with("my-workflow")
    mock_workflow_manager.delete_workflow.assert_called_with("my-workflow")
    mock_workflow_manager.get_singlejob_status.assert_called_with("my-job")
    mock_workflow_manager.abort_singlejob.assert_called_with("my-job")


def test_fastapi_app_metadata(fastapi_thread):
    """Test FastAPI app has correct metadata"""
    assert fastapi_thread.app.title == "SimStackServer API"
    assert "SimStackServer workflow management" in fastapi_thread.app.description
    assert fastapi_thread.app.version == "1.0.0"


def test_endpoint_special_characters_in_ids(test_client, mock_workflow_manager):
    """Test endpoints handle special characters in workflow/job IDs"""
    # Test with URL-encoded special characters
    workflow_id = "workflow-with-dashes"
    job_id = "job_with_underscores"

    response = test_client.get(f"/api/workflows/{workflow_id}/jobs")
    assert response.status_code == 200
    mock_workflow_manager.list_jobs_of_workflow.assert_called_with(workflow_id)

    response = test_client.post(f"/api/singlejobs/{job_id}/abort")
    assert response.status_code == 200
    mock_workflow_manager.abort_singlejob.assert_called_with(job_id)


def test_logger_usage(mock_simstack_server):
    """Test that logger is used correctly"""
    with patch("SimStackServer.FastAPIServer.logging.getLogger") as mock_get_logger:
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        thread = FastAPIThread(mock_simstack_server, host="127.0.0.1", port=8005)

        # Verify logger was obtained
        mock_get_logger.assert_called_once_with("FastAPIThread")
        assert thread._logger == mock_logger


def test_empty_workflow_lists(test_client, mock_workflow_manager):
    """Test endpoints with empty workflow lists"""
    mock_workflow_manager.get_inprogress_workflows.return_value = []
    mock_workflow_manager.get_finished_workflows.return_value = []

    response = test_client.get("/api/workflows")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["inprogress"]) == 0
    assert len(data["finished"]) == 0


def test_empty_job_list(test_client, mock_workflow_manager):
    """Test workflow with no jobs"""
    mock_workflow_manager.list_jobs_of_workflow.return_value = []

    response = test_client.get("/api/workflows/wf1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert len(data["jobs"]) == 0


# ==================== New Endpoint Tests (Workflow/Job Submission, HTTP Server, etc.) ====================


def test_submit_workflow(test_client, mock_simstack_server):
    """Test submitting a workflow for execution"""
    from queue import Queue
    mock_simstack_server._submitted_workflow_queue = Queue()
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/home/user/{x}"

    response = test_client.post(
        "/api/workflows/submit",
        json={"filename": "path/to/workflow.xml"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert data["filename"] == "path/to/workflow.xml"
    assert "submitted for execution" in data["message"]

    # Verify workflow was added to queue
    assert not mock_simstack_server._submitted_workflow_queue.empty()
    submitted_filename = mock_simstack_server._submitted_workflow_queue.get()
    assert submitted_filename == "/home/user/path/to/workflow.xml"


def test_submit_workflow_absolute_path(test_client, mock_simstack_server):
    """Test submitting a workflow with absolute path"""
    from queue import Queue
    mock_simstack_server._submitted_workflow_queue = Queue()
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: x if x.startswith('/') else f"/home/user/{x}"

    response = test_client.post(
        "/api/workflows/submit",
        json={"filename": "/absolute/path/to/workflow.xml"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"

    submitted_filename = mock_simstack_server._submitted_workflow_queue.get()
    assert submitted_filename == "/absolute/path/to/workflow.xml"


def test_submit_singlejob(test_client, mock_simstack_server):
    """Test submitting a single job for execution"""
    from queue import Queue
    mock_simstack_server._submitted_singlejob_queue = Queue()
    mock_simstack_server._external_job_uid_to_jobid = {}

    # Create a mock WFEM dict
    wfem_dict = {
        "uid": "test-job-123",
        "storage": "/path/to/storage",
        "resources": {"queueing_system": "Internal"},
    }

    response = test_client.post(
        "/api/singlejobs/submit",
        json={"wfem": wfem_dict}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert data["job_uid"] == "test-job-123"
    assert "submitted for execution" in data["message"]

    # Verify job was added to queue
    assert not mock_simstack_server._submitted_singlejob_queue.empty()
    assert "test-job-123" in mock_simstack_server._external_job_uid_to_jobid
    assert mock_simstack_server._external_job_uid_to_jobid["test-job-123"] == -1


def test_get_http_server_new_server(test_client, mock_simstack_server, fastapi_thread):
    """Test getting HTTP server info when no server exists"""
    mock_simstack_server._http_server = None
    mock_simstack_server._start_http_server = Mock(return_value=("testuser", "testpass", 8080))
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/abs/{x}"

    response = test_client.post(
        "/api/http-server",
        json={"basefolder": "path/to/folder"}
    )
    assert response.status_code == 200
    data = response.json()
    # Now returns FastAPI port instead of old HTTP server port
    assert data["port"] == fastapi_thread.port
    assert data["user"] == "testuser"
    assert data["password"] == "testpass"
    # URL now points to FastAPI browse endpoint
    assert "/http/browse/" in data["url"]

    # Verify start_http_server was called for backwards compatibility
    mock_simstack_server._start_http_server.assert_called_once_with(directory="path/to/folder")


def test_get_http_server_existing_server(test_client, mock_simstack_server, fastapi_thread):
    """Test getting HTTP server info when server already exists"""
    mock_http_server = Mock()
    mock_http_server.is_alive.return_value = True
    mock_simstack_server._http_server = mock_http_server
    mock_simstack_server._http_user = "existing_user"
    mock_simstack_server._http_pass = "existing_pass"
    mock_simstack_server._http_port = 9090
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/abs/{x}"

    response = test_client.post(
        "/api/http-server",
        json={"basefolder": "path/to/folder"}
    )
    assert response.status_code == 200
    data = response.json()
    # Now returns FastAPI port instead of old HTTP server port
    assert data["port"] == fastapi_thread.port
    assert data["user"] == "existing_user"
    assert data["password"] == "existing_pass"
    # URL now points to FastAPI browse endpoint
    assert "/http/browse/" in data["url"]


def test_get_http_server_dead_server(test_client, mock_simstack_server, fastapi_thread):
    """Test getting HTTP server info when server exists but is dead"""
    mock_http_server = Mock()
    mock_http_server.is_alive.return_value = False
    mock_simstack_server._http_server = mock_http_server
    mock_simstack_server._start_http_server = Mock(return_value=("newuser", "newpass", 8081))
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/abs/{x}"

    response = test_client.post(
        "/api/http-server",
        json={"basefolder": "path/to/folder"}
    )
    assert response.status_code == 200
    data = response.json()
    # Now returns FastAPI port instead of old HTTP server port
    assert data["port"] == fastapi_thread.port
    assert data["user"] == "newuser"
    assert data["password"] == "newpass"
    # URL now points to FastAPI browse endpoint
    assert "/http/browse/" in data["url"]

    # Verify start_http_server was called to restart
    mock_simstack_server._start_http_server.assert_called_once()


def test_shutdown_server(test_client, mock_simstack_server):
    """Test shutting down the server"""
    mock_simstack_server._stop_main = False
    mock_simstack_server._stop_thread = False

    response = test_client.post("/api/server/shutdown")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "shutting_down"
    assert "shutdown has been initiated" in data["message"]

    # Verify stop flags were set
    assert mock_simstack_server._stop_main is True
    assert mock_simstack_server._stop_thread is True


def test_clear_server_state(test_client, mock_simstack_server):
    """Test clearing server state"""
    mock_simstack_server._clear_server_state = Mock()

    response = test_client.post("/api/server/clear-state")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cleared"
    assert "state has been cleared" in data["message"]

    # Verify clear_server_state was called
    mock_simstack_server._clear_server_state.assert_called_once()


# ==================== Error Handling Tests for New Endpoints ====================


def test_submit_workflow_error(test_client, mock_simstack_server):
    """Test error handling when workflow submission fails"""
    mock_simstack_server._remote_relative_to_absolute_filename = Mock(side_effect=Exception("Path resolution failed"))

    response = test_client.post(
        "/api/workflows/submit",
        json={"filename": "bad/path/workflow.xml"}
    )
    assert response.status_code == 500
    assert "Path resolution failed" in response.json()["detail"]


def test_submit_singlejob_error(test_client, mock_simstack_server):
    """Test error handling when single job submission fails"""
    from queue import Queue
    mock_simstack_server._submitted_singlejob_queue = Queue()
    mock_simstack_server._external_job_uid_to_jobid = {}

    # Mock Queue.put to raise an exception
    mock_simstack_server._submitted_singlejob_queue.put = Mock(side_effect=Exception("Queue full"))

    # Provide a minimal valid WFEM dict
    wfem_dict = {
        "uid": "test-job-error",
        "storage": "/path/to/storage",
        "resources": {"queueing_system": "Internal"},
    }

    response = test_client.post(
        "/api/singlejobs/submit",
        json={"wfem": wfem_dict}
    )
    assert response.status_code == 500
    assert "Queue full" in response.json()["detail"]


def test_get_http_server_error(test_client, mock_simstack_server):
    """Test error handling when HTTP server startup fails"""
    mock_simstack_server._http_server = None
    mock_simstack_server._start_http_server = Mock(side_effect=Exception("Port already in use"))

    response = test_client.post(
        "/api/http-server",
        json={"basefolder": "path/to/folder"}
    )
    assert response.status_code == 500
    assert "Port already in use" in response.json()["detail"]


def test_shutdown_server_error(test_client, mock_simstack_server):
    """Test error handling when server shutdown fails"""
    # Make setting _stop_main raise an exception
    type(mock_simstack_server)._stop_main = property(
        lambda self: None,
        lambda self, value: (_ for _ in ()).throw(Exception("Cannot shutdown"))
    )

    response = test_client.post("/api/server/shutdown")
    assert response.status_code == 500
    assert "Cannot shutdown" in response.json()["detail"]


def test_clear_server_state_error(test_client, mock_simstack_server):
    """Test error handling when clearing server state fails"""
    mock_simstack_server._clear_server_state = Mock(side_effect=Exception("Clear failed"))

    response = test_client.post("/api/server/clear-state")
    assert response.status_code == 500
    assert "Clear failed" in response.json()["detail"]


# ==================== Integration Tests for New Endpoints ====================


def test_submit_multiple_workflows(test_client, mock_simstack_server):
    """Test submitting multiple workflows"""
    from queue import Queue
    mock_simstack_server._submitted_workflow_queue = Queue()
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/home/user/{x}"

    workflows = ["wf1.xml", "wf2.xml", "wf3.xml"]
    for wf in workflows:
        response = test_client.post(
            "/api/workflows/submit",
            json={"filename": wf}
        )
        assert response.status_code == 200

    # Verify all workflows were queued
    assert mock_simstack_server._submitted_workflow_queue.qsize() == 3


def test_submit_multiple_singlejobs(test_client, mock_simstack_server):
    """Test submitting multiple single jobs"""
    from queue import Queue
    mock_simstack_server._submitted_singlejob_queue = Queue()
    mock_simstack_server._external_job_uid_to_jobid = {}

    job_uids = ["job-1", "job-2", "job-3"]
    for uid in job_uids:
        wfem_dict = {
            "uid": uid,
            "storage": f"/path/to/{uid}",
            "resources": {"queueing_system": "Internal"},
        }
        response = test_client.post(
            "/api/singlejobs/submit",
            json={"wfem": wfem_dict}
        )
        assert response.status_code == 200

    # Verify all jobs were queued
    assert mock_simstack_server._submitted_singlejob_queue.qsize() == 3
    for uid in job_uids:
        assert uid in mock_simstack_server._external_job_uid_to_jobid


def test_workflow_lifecycle_via_api(test_client, mock_simstack_server, mock_workflow_manager):
    """Test complete workflow lifecycle: submit -> list -> abort -> delete"""
    from queue import Queue
    mock_simstack_server._submitted_workflow_queue = Queue()
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/home/user/{x}"

    # Submit
    response = test_client.post(
        "/api/workflows/submit",
        json={"filename": "lifecycle_test.xml"}
    )
    assert response.status_code == 200

    # List
    response = test_client.get("/api/workflows")
    assert response.status_code == 200

    # Abort
    response = test_client.post("/api/workflows/wf1/abort")
    assert response.status_code == 200

    # Delete
    response = test_client.delete("/api/workflows/wf1")
    assert response.status_code == 200


# ==================== File Operations Tests ====================


@pytest.fixture
def temp_basepath():
    """Create a temporary directory for file operations testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_simstack_server_with_basepath(mock_workflow_manager, temp_basepath):
    """Create a mock SimStackServer with a config that has a basepath"""
    server = Mock()
    server._workflow_manager = mock_workflow_manager

    # Mock the config
    mock_config = Mock()
    mock_config.get_calculation_basepath.return_value = temp_basepath
    server._config = mock_config

    return server


@pytest.fixture
def file_ops_test_client(mock_simstack_server_with_basepath):
    """Create a TestClient for file operations testing"""
    thread = FastAPIThread(mock_simstack_server_with_basepath, host="127.0.0.1", port=8010)
    return TestClient(thread.app)


def test_file_exists_endpoint_file_exists(file_ops_test_client, temp_basepath):
    """Test checking if a file exists - file exists"""
    # Create a test file
    test_file = "test_file.txt"
    with open(os.path.join(temp_basepath, test_file), "w") as f:
        f.write("test content")

    response = file_ops_test_client.post(
        "/api/files/exists",
        json={"filename": test_file}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["path"] == test_file
    assert data["is_directory"] is False


def test_file_exists_endpoint_directory_exists(file_ops_test_client, temp_basepath):
    """Test checking if a directory exists"""
    # Create a test directory
    test_dir = "test_directory"
    os.makedirs(os.path.join(temp_basepath, test_dir))

    response = file_ops_test_client.post(
        "/api/files/exists",
        json={"filename": test_dir}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["path"] == test_dir
    assert data["is_directory"] is True


def test_file_exists_endpoint_not_exists(file_ops_test_client):
    """Test checking if a file exists - file does not exist"""
    response = file_ops_test_client.post(
        "/api/files/exists",
        json={"filename": "nonexistent_file.txt"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert data["path"] == "nonexistent_file.txt"
    assert data["is_directory"] is None


def test_list_directory_success(file_ops_test_client, temp_basepath):
    """Test listing directory contents"""
    # Create test files and directories
    os.makedirs(os.path.join(temp_basepath, "test_dir"))
    with open(os.path.join(temp_basepath, "test_dir", "file1.txt"), "w") as f:
        f.write("content1")
    with open(os.path.join(temp_basepath, "test_dir", "file2.txt"), "w") as f:
        f.write("content2")
    os.makedirs(os.path.join(temp_basepath, "test_dir", "subdir"))

    response = file_ops_test_client.post(
        "/api/files/list",
        json={"path": "test_dir"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["files"]) == 3

    # Check file types
    file_names = {f["name"]: f["type"] for f in data["files"]}
    assert file_names["file1.txt"] == "f"
    assert file_names["file2.txt"] == "f"
    assert file_names["subdir"] == "d"


def test_list_directory_not_found(file_ops_test_client):
    """Test listing a directory that doesn't exist"""
    response = file_ops_test_client.post(
        "/api/files/list",
        json={"path": "nonexistent_dir"}
    )
    assert response.status_code == 404
    assert "Directory not found" in response.json()["detail"]


def test_list_directory_not_a_directory(file_ops_test_client, temp_basepath):
    """Test listing a path that is not a directory"""
    # Create a file
    with open(os.path.join(temp_basepath, "not_a_dir.txt"), "w") as f:
        f.write("content")

    response = file_ops_test_client.post(
        "/api/files/list",
        json={"path": "not_a_dir.txt"}
    )
    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"]


def test_create_directory_success(file_ops_test_client, temp_basepath):
    """Test creating a directory"""
    response = file_ops_test_client.post(
        "/api/files/mkdir",
        json={"directory": "new_dir/nested/deeply"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] is True
    assert data["path"] == "new_dir/nested/deeply"
    assert os.path.isdir(os.path.join(temp_basepath, "new_dir/nested/deeply"))


def test_create_directory_already_exists(file_ops_test_client, temp_basepath):
    """Test creating a directory that already exists"""
    os.makedirs(os.path.join(temp_basepath, "existing_dir"))

    response = file_ops_test_client.post(
        "/api/files/mkdir",
        json={"directory": "existing_dir"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] is False
    assert data["path"] == "existing_dir"


def test_create_directory_path_is_file(file_ops_test_client, temp_basepath):
    """Test creating a directory where a file exists"""
    with open(os.path.join(temp_basepath, "existing_file.txt"), "w") as f:
        f.write("content")

    response = file_ops_test_client.post(
        "/api/files/mkdir",
        json={"directory": "existing_file.txt"}
    )
    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"]


def test_delete_file_success(file_ops_test_client, temp_basepath):
    """Test deleting a file"""
    # Create a test file
    test_file = "file_to_delete.txt"
    filepath = os.path.join(temp_basepath, test_file)
    with open(filepath, "w") as f:
        f.write("content")

    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/delete",
        json={"filename": test_file}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] is True
    assert data["path"] == test_file
    assert not os.path.exists(filepath)


def test_delete_file_not_found(file_ops_test_client):
    """Test deleting a file that doesn't exist"""
    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/delete",
        json={"filename": "nonexistent.txt"}
    )
    assert response.status_code == 404
    assert "File not found" in response.json()["detail"]


def test_delete_file_is_directory(file_ops_test_client, temp_basepath):
    """Test deleting a file that is actually a directory"""
    os.makedirs(os.path.join(temp_basepath, "is_a_dir"))

    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/delete",
        json={"filename": "is_a_dir"}
    )
    assert response.status_code == 400
    assert "use /api/files/rmtree" in response.json()["detail"]


def test_remove_directory_tree_success(file_ops_test_client, temp_basepath):
    """Test removing a directory tree"""
    # Create a directory tree
    test_dir = os.path.join(temp_basepath, "dir_to_remove")
    os.makedirs(os.path.join(test_dir, "subdir"))
    with open(os.path.join(test_dir, "file.txt"), "w") as f:
        f.write("content")
    with open(os.path.join(test_dir, "subdir", "file2.txt"), "w") as f:
        f.write("content2")

    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/rmtree",
        json={"dirname": "dir_to_remove"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] is True
    assert data["path"] == "dir_to_remove"
    assert not os.path.exists(test_dir)


def test_remove_directory_tree_not_exists(file_ops_test_client):
    """Test removing a directory that doesn't exist"""
    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/rmtree",
        json={"dirname": "nonexistent_dir"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] is False
    assert "does not exist" in data["message"]


def test_remove_directory_tree_not_a_directory(file_ops_test_client, temp_basepath):
    """Test removing a path that is not a directory"""
    with open(os.path.join(temp_basepath, "is_a_file.txt"), "w") as f:
        f.write("content")

    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/rmtree",
        json={"dirname": "is_a_file.txt"}
    )
    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"]


def test_upload_file_success(file_ops_test_client, temp_basepath):
    """Test uploading a file"""
    file_content = b"Test file content"
    files = {"file": ("test_upload.txt", BytesIO(file_content), "text/plain")}

    response = file_ops_test_client.post(
        "/api/files/upload",
        files=files,
        data={"to_file": "uploads/test_upload.txt"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["path"] == "uploads/test_upload.txt"

    # Verify file was created
    uploaded_file = os.path.join(temp_basepath, "uploads", "test_upload.txt")
    assert os.path.exists(uploaded_file)
    with open(uploaded_file, "rb") as f:
        assert f.read() == file_content


def test_upload_file_default_name(file_ops_test_client, temp_basepath):
    """Test uploading a file with default filename"""
    file_content = b"Test file content"
    files = {"file": ("default_name.txt", BytesIO(file_content), "text/plain")}

    response = file_ops_test_client.post(
        "/api/files/upload",
        files=files
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Verify file was created with default name
    uploaded_file = os.path.join(temp_basepath, "default_name.txt")
    assert os.path.exists(uploaded_file)


def test_download_file_success(file_ops_test_client, temp_basepath):
    """Test downloading a file"""
    # Create a test file
    test_file = "download_test.txt"
    file_content = "Test download content"
    with open(os.path.join(temp_basepath, test_file), "w") as f:
        f.write(file_content)

    response = file_ops_test_client.get(
        "/api/files/download",
        params={"from_file": test_file}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content.decode() == file_content


def test_download_file_not_found(file_ops_test_client):
    """Test downloading a file that doesn't exist"""
    response = file_ops_test_client.get(
        "/api/files/download",
        params={"from_file": "nonexistent.txt"}
    )
    assert response.status_code == 404
    assert "File not found" in response.json()["detail"]


def test_download_file_is_directory(file_ops_test_client, temp_basepath):
    """Test downloading a path that is a directory"""
    os.makedirs(os.path.join(temp_basepath, "is_a_dir"))

    response = file_ops_test_client.get(
        "/api/files/download",
        params={"from_file": "is_a_dir"}
    )
    assert response.status_code == 400
    assert "directory" in response.json()["detail"]


def test_basepath_override(file_ops_test_client, temp_basepath):
    """Test using basepath_override parameter"""
    # Create a different temp directory
    override_path = tempfile.mkdtemp()
    try:
        # Create a file in the override path
        with open(os.path.join(override_path, "test.txt"), "w") as f:
            f.write("override content")

        response = file_ops_test_client.post(
            "/api/files/exists",
            json={"filename": "test.txt", "basepath_override": override_path}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
    finally:
        shutil.rmtree(override_path, ignore_errors=True)


def test_file_operations_with_nested_paths(file_ops_test_client, temp_basepath):
    """Test file operations with nested directory paths"""
    # Create nested directories
    nested_path = "level1/level2/level3"
    response = file_ops_test_client.post(
        "/api/files/mkdir",
        json={"directory": nested_path}
    )
    assert response.status_code == 200

    # Upload a file to nested path
    file_content = b"Nested file content"
    files = {"file": ("nested.txt", BytesIO(file_content), "text/plain")}
    response = file_ops_test_client.post(
        "/api/files/upload",
        files=files,
        data={"to_file": f"{nested_path}/nested.txt"}
    )
    assert response.status_code == 200

    # List the nested directory
    response = file_ops_test_client.post(
        "/api/files/list",
        json={"path": nested_path}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["files"][0]["name"] == "nested.txt"

    # Download the file
    response = file_ops_test_client.get(
        "/api/files/download",
        params={"from_file": f"{nested_path}/nested.txt"}
    )
    assert response.status_code == 200
    assert response.content == file_content

    # Delete the entire tree
    response = file_ops_test_client.request(
        "DELETE",
        "/api/files/rmtree",
        json={"dirname": "level1"}
    )
    assert response.status_code == 200
    assert not os.path.exists(os.path.join(temp_basepath, "level1"))


# ==================== HTTP Server Directory Browsing Tests ====================


@pytest.fixture
def http_browse_test_client(mock_simstack_server_with_basepath, temp_basepath):
    """Create a TestClient for HTTP browsing with base directory set"""
    thread = FastAPIThread(mock_simstack_server_with_basepath, host="127.0.0.1", port=8011)
    # Set base directory for browsing
    thread._http_base_directory = temp_basepath
    return TestClient(thread.app), temp_basepath


def test_serve_static_css(test_client):
    """Test serving static CSS file"""
    response = test_client.get("/http/static/dirlist.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"] or "text/plain" in response.headers["content-type"]


def test_serve_static_favicon(test_client):
    """Test serving static favicon"""
    response = test_client.get("/http/static/favicon.ico")
    assert response.status_code == 200
    # Favicon should be served with appropriate image type


def test_serve_static_file_not_found(test_client):
    """Test serving non-existent static file"""
    response = test_client.get("/http/static/nonexistent.css")
    assert response.status_code == 404


def test_serve_static_file_directory_traversal(test_client):
    """Test that directory traversal is prevented for static files"""
    response = test_client.get("/http/static/../../../etc/passwd")
    assert response.status_code in [403, 404]


def test_browse_directory_listing(http_browse_test_client):
    """Test browsing a directory with HTML listing"""
    client, temp_basepath = http_browse_test_client

    # Create test files
    os.makedirs(os.path.join(temp_basepath, "test_dir"))
    with open(os.path.join(temp_basepath, "test_dir", "file1.txt"), "w") as f:
        f.write("content1")
    with open(os.path.join(temp_basepath, "test_dir", "file2.log"), "w") as f:
        f.write("content2")

    response = client.get("/http/browse/test_dir")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    # Check HTML content
    html_content = response.text
    assert "Directory listing" in html_content
    assert "file1.txt" in html_content
    assert "file2.log" in html_content
    assert "dirlist.css" in html_content  # CSS should be linked


def test_browse_root_directory(http_browse_test_client):
    """Test browsing the root directory"""
    client, temp_basepath = http_browse_test_client

    # Create some test files in root
    with open(os.path.join(temp_basepath, "root_file.txt"), "w") as f:
        f.write("root content")

    response = client.get("/http/browse")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "root_file.txt" in response.text


def test_browse_serve_file(http_browse_test_client):
    """Test serving a file through the browse endpoint"""
    client, temp_basepath = http_browse_test_client

    # Create a test file
    test_content = "This is test content for serving"
    with open(os.path.join(temp_basepath, "serve_test.txt"), "w") as f:
        f.write(test_content)

    response = client.get("/http/browse/serve_test.txt")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.text == test_content


def test_browse_custom_mime_types(http_browse_test_client):
    """Test that custom MIME types are applied correctly"""
    client, temp_basepath = http_browse_test_client

    # Test various custom extensions
    custom_files = {
        "test.log": "log content",
        "test.sh": "#!/bin/bash\necho test",
        "test.json": '{"key": "value"}',
        "test.stderr": "error output",
    }

    for filename, content in custom_files.items():
        with open(os.path.join(temp_basepath, filename), "w") as f:
            f.write(content)

        response = client.get(f"/http/browse/{filename}")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


def test_browse_directory_not_found(http_browse_test_client):
    """Test browsing a non-existent directory"""
    client, _ = http_browse_test_client

    response = client.get("/http/browse/nonexistent_dir")
    assert response.status_code == 404


def test_browse_directory_traversal_blocked(http_browse_test_client):
    """Test that directory traversal attacks are blocked"""
    client, _ = http_browse_test_client

    # Attempt directory traversal
    response = client.get("/http/browse/../../../etc/passwd")
    # Should return either 403 (access denied) or 404 (path not found after normalization)
    # The important thing is it's not 200 (successfully serving the file)
    assert response.status_code in [403, 404]


def test_browse_without_base_directory():
    """Test browsing when base directory is not set"""
    mock_server = Mock()
    mock_server._workflow_manager = Mock()
    thread = FastAPIThread(mock_server, host="127.0.0.1", port=8012)
    # Don't set _http_base_directory
    client = TestClient(thread.app)

    response = client.get("/http/browse/some_path")
    assert response.status_code == 400
    assert "base directory not set" in response.text.lower()


def test_browse_nested_directories(http_browse_test_client):
    """Test browsing nested directory structures"""
    client, temp_basepath = http_browse_test_client

    # Create nested structure
    nested_path = os.path.join(temp_basepath, "level1", "level2", "level3")
    os.makedirs(nested_path)
    with open(os.path.join(nested_path, "deep_file.txt"), "w") as f:
        f.write("deep content")

    # Browse to nested directory
    response = client.get("/http/browse/level1/level2/level3")
    assert response.status_code == 200
    assert "deep_file.txt" in response.text

    # Serve file from nested directory
    response = client.get("/http/browse/level1/level2/level3/deep_file.txt")
    assert response.status_code == 200
    assert response.text == "deep content"


def test_browse_file_metadata_in_listing(http_browse_test_client):
    """Test that file metadata is shown in directory listing"""
    client, temp_basepath = http_browse_test_client

    # Create a file with known size
    test_file = os.path.join(temp_basepath, "metadata_test.txt")
    with open(test_file, "w") as f:
        f.write("x" * 1024)  # 1 KiB

    response = client.get("/http/browse")
    assert response.status_code == 200

    html_content = response.text
    assert "metadata_test.txt" in html_content
    # Should show file size
    assert "KiB" in html_content or "B" in html_content
    # Should show file type
    assert "File" in html_content


def test_browse_symlink_handling(http_browse_test_client):
    """Test that symlinks are handled correctly"""
    client, temp_basepath = http_browse_test_client

    # Create a file and a symlink to it
    target_file = os.path.join(temp_basepath, "target.txt")
    with open(target_file, "w") as f:
        f.write("target content")

    symlink_path = os.path.join(temp_basepath, "link.txt")
    try:
        os.symlink(target_file, symlink_path)

        # Browse should show the symlink
        response = client.get("/http/browse")
        assert response.status_code == 200
        # Symlinks are marked with @
        assert "link.txt@" in response.text or "link.txt" in response.text
    except OSError:
        # Skip test if symlinks are not supported (e.g., on Windows)
        pytest.skip("Symlinks not supported on this system")


def test_human_readable_size_helper():
    """Test the human readable size helper function"""
    from SimStackServer.FastAPIServer import FastAPIThread

    assert FastAPIThread._human_readable_size(100) == "100.00B"
    assert FastAPIThread._human_readable_size(1024) == "1.00KiB"
    assert FastAPIThread._human_readable_size(1024 * 1024) == "1.00MiB"
    assert FastAPIThread._human_readable_size(1024 * 1024 * 1024) == "1.00GiB"


def test_guess_mime_type_helper():
    """Test the MIME type guessing helper function"""
    from SimStackServer.FastAPIServer import FastAPIThread

    # Test custom types
    assert FastAPIThread._guess_mime_type("test.log") == "text/plain"
    assert FastAPIThread._guess_mime_type("test.sh") == "text/plain"
    assert FastAPIThread._guess_mime_type("test.json") == "text/plain"

    # Test standard types
    assert "html" in FastAPIThread._guess_mime_type("test.html")
    assert "image" in FastAPIThread._guess_mime_type("test.png")


def test_http_server_endpoint_sets_base_directory(test_client, mock_simstack_server):
    """Test that /api/http-server sets the base directory for browsing"""
    from queue import Queue
    mock_simstack_server._http_server = None
    mock_simstack_server._start_http_server = Mock(return_value=("user", "pass", 8080))
    mock_simstack_server._remote_relative_to_absolute_filename = lambda x: f"/abs/{x}"

    response = test_client.post(
        "/api/http-server",
        json={"basefolder": "test/folder"}
    )
    assert response.status_code == 200
    data = response.json()

    # Should return FastAPI port, not old HTTP server port
    assert data["url"].endswith("/http/browse/")
