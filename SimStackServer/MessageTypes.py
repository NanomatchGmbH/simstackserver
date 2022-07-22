from enum import IntEnum, auto

import msgpack
#Alias here to be able to switch to json
mypacker = msgpack

class InvalidMessageError(Exception):
    pass

class JobStatus(IntEnum):
    QUEUED = 1
    RUNNING = 2
    READY = 3
    FAILED = 4
    SUCCESSFUL = 5
    ABORTED = 6
    MARKED_FOR_DELETION = 7


class SSS_MESSAGETYPE(IntEnum):
    CONNECT = 1
    ACK = 2
    LISTWFS = 3
    LISTWFSREPLY = 4
    LISTWFJOBS = 5
    LISTWFJOBSREPLY = 6
    DELWF = 7
    ABORTWF = 8
    ABORTJOB = 9
    DELJOB = 10
    DISCONNECT = 11
    SUBMITWF = 12
    GETHTTPSERVER = 13
    GETSINGLEJOBSTATUS = 14
    GETSINGLEJOBSTATUSREPLY = 15
    ABORTSINGLEJOB = 16
    NOOP = 17
    SHUTDOWN = 18
    SUBMITSINGLEJOB = 19
    CLEARSERVERSTATE = 20 # This message type should just be used for testing. It will completely clear the server state.


class ResourceStatus(IntEnum):
    READY = 1
    UNAVAILABLE = 2

class ErrorCodes(IntEnum):
    NO_ERROR = 1
    NOT_CONNECTED = 2
    DECODE_ERROR = 3
    MALFORMED_JSON = 4
    EMPTY_RESPONSE = 5
    NOT_A_FILE = 6
    INVALID_QUERY = 7
    INVALID_SETUP = 8
    HTTP_ERROR = 9
    CONN_TIMEOUT = 10
    REQ_TIMEOUT = 11
    SSL_ERROR = 12
    CONN_ERROR = 13
    UNKONWN_EXCPTION = 14
    FILE_IO_ERROR = 15
    REMOTE_FILE_NOT_FOUND = 16
    RESOURCE_DOES_NOT_EXIST = 17
    INVALID_CREDENTIALS = 18

class ConnectionState(IntEnum):
    """
    Connection state machine:
        NOT_SETUP
            |
            | - setup
            |/---------- setup ----\------\
            |                        \     \
        DISCONNECTED------------\     |     |
            |  \                 \    |     |
            |   \---------------------/     |
            |                     |         |
            | - connect           |         |
            |/--------- connect -------- FAILED
        CONNECTING                |         |
            |                     |         |
            |--[fail]-----------------------|
            |                     |         |
        [success]                 |         |
            |                     |         |
        CONNECTED                 |         |
            |                     |         |
            |--[fail]----------------------/
            | - disconnect        |
            |                     |
        DISCONNECTING             |
            |                     |
             \___________________/
    """

    CONNECTED = 1
    CONNECTING = 2
    DISCONNECTED = 3
    DISCONNECTING = 4
    NOT_SETUP = 5
    FAILED = 6


class Message(object):
    @classmethod
    def connect_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.CONNECT}
        return mypacker.dumps(mydict)

    @classmethod
    def ack_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.ACK}
        return mypacker.dumps(mydict)

    @classmethod
    def noop_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.NOOP}
        return mypacker.dumps(mydict)

    @classmethod
    def shutdown_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.SHUTDOWN}
        return mypacker.dumps(mydict)

    @classmethod
    def getsinglejobstatus_message(cls, wfem_uid: str):
        mydict = {"MessageType": SSS_MESSAGETYPE.GETSINGLEJOBSTATUS,
                  "WFEM_UID": wfem_uid}
        return mypacker.dumps(mydict)

    @classmethod
    def getsinglejobstatus_message_reply(cls, reply: str):
        mydict = {"MessageType": SSS_MESSAGETYPE.GETSINGLEJOBSTATUSREPLY,
                  "status": reply}
        return mypacker.dumps(mydict)

    @classmethod
    def clearserverstate_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.CLEARSERVERSTATE}
        return mypacker.dumps(mydict)

    @classmethod
    def abortsinglejob_message(cls, wfem_uid: str):
        mydict = {"MessageType": SSS_MESSAGETYPE.ABORTSINGLEJOB,
                  "WFEM_UID": wfem_uid}
        return mypacker.dumps(mydict)

    """
        The two next functions exist in case we need to fumble with encoding.
        ... which turned out to be true
    """
    @staticmethod
    def _loads(message):
        return mypacker.loads(message, raw = False, strict_map_key = False)

    @staticmethod
    def _dumps(indict):
        return mypacker.dumps(indict, use_bin_type = True)

    @classmethod
    def unpack(cls, message):
        #Another indirection in case we want to remove MessageType somehow.

        upack = cls._loads(message)
        if not "MessageType" in upack:
            raise InvalidMessageError("MessageType not found in Message. Message was: %s"%upack)
        messagetype = upack["MessageType"]
        return messagetype, upack

    @classmethod
    def dict_message(cls, message_type, indict):
        indict["MessageType"] = message_type
        return cls._dumps(indict)

    @classmethod
    def _empty_dict_with_messagetype(cls, messagetype):
        return {"MessageType" : messagetype}

    @classmethod
    def list_wfs_message(cls):
        return cls._dumps(cls._empty_dict_with_messagetype(SSS_MESSAGETYPE.LISTWFS))

    @classmethod
    def delete_wf_message(cls, workflow_submit_name):
        mydict = {
            "workflow_submit_name": workflow_submit_name
        }
        return cls.dict_message(SSS_MESSAGETYPE.DELWF, mydict)

    @classmethod
    def list_jobs_of_wf_message(cls, workflow_submit_name):
        mydict = {
            "workflow_submit_name": workflow_submit_name
        }
        return cls.dict_message(SSS_MESSAGETYPE.LISTWFJOBS, mydict)

    @classmethod
    def get_http_server_request_message(cls, basefolder):
        mydict = {
            "basefolder": basefolder
        }
        return cls.dict_message(SSS_MESSAGETYPE.GETHTTPSERVER, mydict)

    @classmethod
    def submit_single_job_message(cls, wfem):
        from SimStackServer.WorkflowModel import WorkflowExecModule
        wfem:WorkflowExecModule
        mydict = {
            "wfem": {}
        }
        wfem.to_dict(mydict["wfem"])
        return cls.dict_message(SSS_MESSAGETYPE.SUBMITSINGLEJOB, mydict)

    @classmethod
    def get_http_server_ack_message(cls, port, user, password):
        mydict = {
            "http_port": port,
            "http_user": user,
            "http_pass": password
        }
        return cls.dict_message(SSS_MESSAGETYPE.GETHTTPSERVER, mydict)

    @classmethod
    def list_jobs_of_wf_message_reply(cls, workflow_submit_name, list_of_jobs):
        mydict = {
            "workflow_submit_name": workflow_submit_name,
            "list_of_jobs": list_of_jobs
        }
        return cls.dict_message(SSS_MESSAGETYPE.LISTWFJOBSREPLY, mydict)

    @classmethod
    def list_wfs_reply_message(cls, wf_info_list):
        mydict = cls._empty_dict_with_messagetype(SSS_MESSAGETYPE.LISTWFSREPLY)
        mydict["workflows"] = wf_info_list
        return cls._dumps(mydict)

    @classmethod
    def submit_wf_message(cls, filename):
        mydict = {
            "filename": filename
        }
        return cls.dict_message(SSS_MESSAGETYPE.SUBMITWF, mydict)

    @classmethod
    def abort_wf_message(cls, workflow_submit_name):
        mydict = {
            "workflow_submit_name": workflow_submit_name
        }
        return cls.dict_message(SSS_MESSAGETYPE.ABORTWF, mydict)