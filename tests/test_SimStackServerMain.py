import pytest
from unittest.mock import Mock, patch
from queue import Queue
from SimStackServer.SimStackServerMain import SimStackServer, MessageTypes, Message


@pytest.fixture
def simstack_server():
    with patch("SimStackServer.SimStackServerMain.SimStackServer._register"):
        server = SimStackServer(my_executable="dummy_executable")
        server._logger = Mock()
        server._workflow_manager = Mock()
        server._clear_server_state = Mock()
        server._start_http_server = Mock(return_value=("user", "pass", 8080))
        server._submitted_singlejob_queue = Mock(spec=Queue)
        server._submitted_workflow_queue = Mock(spec=Queue)
        server._external_job_uid_to_jobid = {}
        yield server


def test_message_handler_connect(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.CONNECT
    message = {}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.connect_message())


def test_message_handler_noop(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.NOOP
    message = {}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.info.assert_called_once_with("Received noop message.")


def test_message_handler_shutdown(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.SHUTDOWN
    message = {}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    assert simstack_server._stop_main is True
    assert simstack_server._stop_thread is True


def test_message_handler_clearserverstate(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.CLEARSERVERSTATE
    message = {}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.info.assert_called_once_with("Hard clearing server state.")
    simstack_server._clear_server_state.assert_called_once()


def test_message_handler_abortwf(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.ABORTWF
    message = {"workflow_submit_name": "test_workflow"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._workflow_manager.abort_workflow.assert_called_once_with(
        "test_workflow"
    )
    simstack_server._logger.debug.assert_called_once_with(
        "Receive workflow abort message test_workflow"
    )


def test_message_handler_abortwf_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.ABORTWF
    message = {"workflow_submit_name": "test_workflow"}
    simstack_server._workflow_manager.abort_workflow.side_effect = Exception(
        "Test error"
    )

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._workflow_manager.abort_workflow.assert_called_once_with(
        "test_workflow"
    )
    simstack_server._logger.exception.assert_called_once_with(
        "Error aborting workflow test_workflow."
    )


def test_message_handler_listwfjobs(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.LISTWFJOBS
    message = {"workflow_submit_name": "test_workflow"}
    simstack_server._workflow_manager.list_jobs_of_workflow.return_value = [
        "job1",
        "job2",
    ]

    simstack_server._message_handler(message_type, message, mock_sock)

    simstack_server._workflow_manager.list_jobs_of_workflow.assert_called_once_with(
        "test_workflow"
    )
    mock_sock.send.assert_called_once_with(
        Message.list_jobs_of_wf_message_reply("test_workflow", ["job1", "job2"])
    )


def test_message_handler_listwfjobs_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.LISTWFJOBS
    message = {"workflow_submit_name": "test_workflow"}
    simstack_server._workflow_manager.list_jobs_of_workflow.side_effect = Exception(
        "Test error"
    )

    simstack_server._message_handler(message_type, message, mock_sock)

    simstack_server._workflow_manager.list_jobs_of_workflow.assert_called_once_with(
        "test_workflow"
    )
    mock_sock.send.assert_called_once_with(
        Message.list_jobs_of_wf_message_reply("test_workflow", [])
    )
    simstack_server._logger.exception.assert_called_once_with(
        "Error listing jobs of workflow test_workflow"
    )


def test_message_handler_delwf(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.DELWF
    message = {"workflow_submit_name": "test_workflow"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._workflow_manager.abort_workflow.assert_called_once_with(
        "test_workflow"
    )
    simstack_server._workflow_manager.delete_workflow.assert_called_once_with(
        "test_workflow"
    )
    simstack_server._logger.debug.assert_called_once_with(
        "Receive workflow delete message test_workflow"
    )


def test_message_handler_delwf_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.DELWF
    message = {"workflow_submit_name": "test_workflow"}
    simstack_server._workflow_manager.abort_workflow.side_effect = Exception(
        "Test error"
    )

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._workflow_manager.abort_workflow.assert_called_once_with(
        "test_workflow"
    )
    simstack_server._logger.exception.assert_called_once_with(
        "Error deleting workflow test_workflow."
    )


def test_message_handler_deljob(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.DELJOB
    message = {"workflow_submit_name": "test_workflow", "job_submit_name": "job1"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.error.assert_called_once_with(
        "DELWF not implemented, however I would like to delete %s from %s"
        % ("job1", "test_workflow")
    )


def test_message_handler_deljob_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.DELJOB
    message = {"invalid_key": "value"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.exception.assert_called_once_with(
        "Error during job deletion."
    )


def test_message_handler_listwfs(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.LISTWFS
    message = {}
    simstack_server._workflow_manager.get_inprogress_workflows.return_value = ["wf1"]
    simstack_server._workflow_manager.get_finished_workflows.return_value = ["wf2"]

    simstack_server._message_handler(message_type, message, mock_sock)

    simstack_server._workflow_manager.get_inprogress_workflows.assert_called_once()
    simstack_server._workflow_manager.get_finished_workflows.assert_called_once()
    mock_sock.send.assert_called_once_with(
        Message.list_wfs_reply_message(["wf1", "wf2"])
    )
    simstack_server._logger.debug.assert_called_once_with("Received LISTWFS message")


def test_message_handler_listwfs_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.LISTWFS
    message = {}
    simstack_server._workflow_manager.get_inprogress_workflows.side_effect = Exception(
        "Test error"
    )

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.list_wfs_reply_message([]))
    simstack_server._logger.exception.assert_called_once_with(
        "Error listing workflows."
    )


def test_message_handler_gethttpserver_new_server(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.GETHTTPSERVER
    message = {"basefolder": "/test/path"}
    simstack_server._http_server = None

    simstack_server._message_handler(message_type, message, mock_sock)

    simstack_server._start_http_server.assert_called_once_with(directory="/test/path")
    mock_sock.send.assert_called_once_with(
        Message.get_http_server_ack_message(8080, "user", "pass")
    )
    assert simstack_server._http_user == "user"
    assert simstack_server._http_pass == "pass"
    assert simstack_server._http_port == 8080


def test_message_handler_gethttpserver_existing_server(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.GETHTTPSERVER
    message = {"basefolder": "/test/path"}
    simstack_server._http_server = Mock(is_alive=lambda: True)
    simstack_server._http_user = "existing_user"
    simstack_server._http_pass = "existing_pass"
    simstack_server._http_port = 9090

    simstack_server._message_handler(message_type, message, mock_sock)

    simstack_server._start_http_server.assert_not_called()
    mock_sock.send.assert_called_once_with(
        Message.get_http_server_ack_message(9090, "existing_user", "existing_pass")
    )


def test_message_handler_submitsinglejob(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.SUBMITSINGLEJOB
    wfem_dict = {"uid": "test_job"}
    message = {"wfem": wfem_dict}

    with patch(
        "SimStackServer.SimStackServerMain.WorkflowExecModule"
    ) as mock_wfem_class:
        mock_wfem = Mock()
        mock_wfem.uid = "test_job"
        mock_wfem_class.return_value = mock_wfem

        simstack_server._message_handler(message_type, message, mock_sock)

        mock_sock.send.assert_called_once_with(Message.ack_message())
        mock_wfem.from_dict.assert_called_once_with(wfem_dict)
        simstack_server._submitted_singlejob_queue.put.assert_called_once_with(
            mock_wfem
        )
        assert simstack_server._external_job_uid_to_jobid["test_job"] == -1


def test_message_handler_submitsinglejob_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.SUBMITSINGLEJOB
    message = {"invalid_key": "value"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.exception.assert_called_once_with(
        "Error submitting single job."
    )


def test_message_handler_abortsinglejob_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.ABORTSINGLEJOB
    message = {"WFEM_UID": "test_job"}
    simstack_server._submitted_singlejob_queue.empty.return_value = True
    simstack_server._workflow_manager.abort_singlejob.side_effect = Exception(
        "Test error"
    )

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.exception.assert_called_once_with(
        "Exception during single job abort message handler."
    )


def test_message_handler_getsinglejobstatus(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.GETSINGLEJOBSTATUS
    message = {"WFEM_UID": "test_job"}
    simstack_server._workflow_manager.get_singlejob_status.return_value = {
        "status": "finished"
    }

    with patch(
        "SimStackServer.SimStackServerMain.Message.getsinglejobstatus_message_reply"
    ) as mock_reply:
        mock_reply.return_value = b"mock_reply"

        simstack_server._message_handler(message_type, message, mock_sock)

        simstack_server._workflow_manager.get_singlejob_status.assert_called_once_with(
            "test_job"
        )
        mock_reply.assert_called_once_with(reply="finished")
        mock_sock.send.assert_called_once_with(b"mock_reply")


def test_message_handler_getsinglejobstatus_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.GETSINGLEJOBSTATUS
    message = {"WFEM_UID": "test_job"}
    simstack_server._workflow_manager.get_singlejob_status.side_effect = Exception(
        "Test error"
    )

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.exception.assert_called_once_with("EXCEPTION RECEIVED")


def test_message_handler_submitwf(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.SUBMITWF
    message = {"filename": "/path/to/workflow.xml"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._submitted_workflow_queue.put.assert_called_once_with(
        "/path/to/workflow.xml"
    )
    simstack_server._logger.debug.assert_called_once_with(
        "Received SUBMITWF message, submitting /path/to/workflow.xml"
    )


def test_message_handler_submitwf_exception(simstack_server):
    mock_sock = Mock()
    message_type = MessageTypes.SUBMITWF
    message = {"invalid_key": "value"}

    simstack_server._message_handler(message_type, message, mock_sock)

    mock_sock.send.assert_called_once_with(Message.ack_message())
    simstack_server._logger.exception.assert_called_once_with(
        "Error submitting workflow."
    )
