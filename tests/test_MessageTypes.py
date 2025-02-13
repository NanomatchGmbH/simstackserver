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
    assert unpacked_message == {'MessageType': 3}

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