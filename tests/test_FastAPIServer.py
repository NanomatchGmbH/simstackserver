import pytest
import time
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

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
