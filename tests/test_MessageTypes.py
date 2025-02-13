import msgpack
import pytest
from SimStackServer.MessageTypes import Message, SSS_MESSAGETYPE, InvalidMessageError


def test_connect_message():
    message = Message.connect_message()
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.CONNECT
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.CONNECT


def test_ack_message():
    message = Message.ack_message()
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.ACK
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.ACK


def test_noop_message():
    message = Message.noop_message()
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.NOOP
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.NOOP


def test_shutdown_message():
    message = Message.shutdown_message()
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.SHUTDOWN
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.SHUTDOWN


def test_getsinglejobstatus_message():
    wfem_uid = "test_uid"
    message = Message.getsinglejobstatus_message(wfem_uid)
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.GETSINGLEJOBSTATUS
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.GETSINGLEJOBSTATUS
    assert unpacked_message["WFEM_UID"] == wfem_uid


def test_getsinglejobstatus_message_reply():
    reply = "test_reply"
    message = Message.getsinglejobstatus_message_reply(reply)
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.GETSINGLEJOBSTATUSREPLY
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.GETSINGLEJOBSTATUSREPLY
    assert unpacked_message["status"] == reply


def test_clearserverstate_message():
    message = Message.clearserverstate_message()
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.CLEARSERVERSTATE
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.CLEARSERVERSTATE


def test_abortsinglejob_message():
    wfem_uid = "test_uid"
    message = Message.abortsinglejob_message(wfem_uid)
    unpacked_type, unpacked_message = Message.unpack(message)
    assert unpacked_type == SSS_MESSAGETYPE.ABORTSINGLEJOB
    assert unpacked_message["MessageType"] == SSS_MESSAGETYPE.ABORTSINGLEJOB
    assert unpacked_message["WFEM_UID"] == wfem_uid


def test_invalid_message_error():
    mymessage = msgpack.dumps({"InvalidKey": "InvalidValue"})
    with pytest.raises(InvalidMessageError):
        Message.unpack(mymessage)


def test_dict_message():
    mymessage = {"MessageKey": "MessageValue"}
    returned_message = Message.dict_message(SSS_MESSAGETYPE.CONNECT, mymessage)
    msg_unpacked = Message.unpack(returned_message)
    assert [k for k in msg_unpacked[1].keys()] == ["MessageKey", "MessageType"]


def test_list_wfs_messages():
    res = Message.list_wfs_message()
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 3
    assert unpacked_message == {"MessageType": 3}


def test_list_jobs_of_wf_message():
    res = Message.list_jobs_of_wf_message("test_wf")
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_message["MessageType"] == 5
    assert unpacked_message["workflow_submit_name"] == "test_wf"


def test_delete_wf_message():
    res = Message.delete_wf_message("test_wf")
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_message["MessageType"] == 7
    assert unpacked_message["workflow_submit_name"] == "test_wf"


def test_get_http_server_request_message():
    res = Message.get_http_server_request_message("test_basefolder")
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_message["MessageType"] == 13
    assert unpacked_message["basefolder"] == "test_basefolder"


def test_submit_single_job_message(workflow_exec_module_fixture):
    res = Message.submit_single_job_message(workflow_exec_module_fixture)
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 19
    ref_dict = {
        "uid": "0c3f3863-c696-42a4-8ff5-4d5e3222d39a",
        "given_name": "TestWFEM",
        "path": "test_path",
        "wano_xml": "test_wano.xml",
        "outputpath": "testdir",
        "original_result_directory": "",
        "inputs": {},
        "outputs": {},
        "exec_command": "echo 'Hello, WorkflowExecModule!'",
        "resources": {
            "resource_name": "<Connected Server>",
            "walltime": "86399",
            "cpus_per_node": "1",
            "nodes": "1",
            "queue": "default",
            "memory": "1GB",
            "custom_requests": "",
            "base_URI": "",
            "port": "22",
            "username": "",
            "basepath": "simstack_workspace",
            "queueing_system": "Internal",
            "sw_dir_on_resource": "/home/nanomatch/nanomatch",
            "extra_config": "None Required (default)",
            "ssh_private_key": "UseSystemDefault",
            "sge_pe": "",
            "reuse_results": "False",
        },
        "runtime_directory": "unstarted",
        "jobid": "unstarted",
        "external_runtime_directory": "",
    }
    assert unpacked_message["wfem"] == ref_dict


def test_get_http_server_ack_message():
    res = Message.get_http_server_ack_message(22, "testuser", "testpw")
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 13
    assert unpacked_message == {
        "MessageType": 13,
        "http_pass": "testpw",
        "http_port": 22,
        "http_user": "testuser",
    }


def test_list_jobs_of_wf_message_reply():
    res = Message.list_jobs_of_wf_message_reply("test_wf", [])
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 6
    assert unpacked_message == {
        "MessageType": 6,
        "list_of_jobs": [],
        "workflow_submit_name": "test_wf",
    }


def test_list_wfs_reply_message():
    res = Message.list_wfs_reply_message([])
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 4
    assert unpacked_message == {"MessageType": 4, "workflows": []}


def test_submit_wf_message():
    res = Message.submit_wf_message("testfile.dat")
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 12
    assert unpacked_message == {"MessageType": 12, "filename": "testfile.dat"}


def test_abort_wf_message():
    res = Message.abort_wf_message("test_wf")
    unpacked_type, unpacked_message = Message.unpack(res)
    assert unpacked_type == 8
    assert unpacked_message == {"MessageType": 8, "workflow_submit_name": "test_wf"}
