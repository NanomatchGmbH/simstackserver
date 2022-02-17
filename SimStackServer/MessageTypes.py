from enum import IntEnum, auto

import msgpack
#Alias here to be able to switch to json
mypacker = msgpack

class InvalidMessageError(Exception):
    pass

class JobStatus(IntEnum):
    """
    List of Job states:

    * QUEUED
    * RUNNING
    * READY
    * FAILED
    * SUCCESSFUL
    * ABORTED
    """
    QUEUED      = auto()
    RUNNING     = auto()
    READY       = auto()
    FAILED      = auto()
    SUCCESSFUL  = auto()
    ABORTED     = auto()
    MARKED_FOR_DELETION = auto()

class SSS_MESSAGETYPE(IntEnum):
    CONNECT = auto()
    ACK = auto()
    LISTWFS = auto()
    LISTWFSREPLY = auto()
    LISTWFJOBS = auto()
    LISTWFJOBSREPLY = auto()
    GETSINGLEJOBSTATUS = auto()
    GETSINGLEJOBSTATUSREPLY = auto()
    ABORTSINGLEJOB = auto()
    #LISTJOBS = auto()
    #LISTJOBSREPLY = auto()
    DELWF = auto()
    ABORTWF = auto()
    ABORTJOB = auto()
    DELJOB = auto()
    DISCONNECT = auto()
    SUBMITWF = auto()
    GETHTTPSERVER = auto()
    NOOP = auto()
    SHUTDOWN = auto()
    SUBMITSINGLEJOB = auto()
    CLEARSERVERSTATE = auto() # This message type should just be used for testing. It will completely clear the server state.


class ResourceStatus(IntEnum):
    """
    List of Resource states:

    * READY
    * UNAVAILABLE
    """
    READY = auto()
    UNAVAILABLE = auto()

class ErrorCodes(IntEnum):
    """
    List of Errors:

    * NO_ERROR
    * NOT_CONNECTED
    * DECODE_ERROR
    * MALFORMED_JSON
    * EMPTY_RESPONSE
    * NOT_A_FILE
    * INVALID_QUERY
    * INVALID_SETUP
    * HTTP_ERROR
    * CONN_TIMEOUT
    * REQ_TIMEOUT
    * SSL_ERROR
    * CONN_ERROR
    * UNKONWN_EXCPTION
    * FILE_IO_ERROR
    * REMOTE_FILE_NOT_FOUND
    * RESOURCE_DOES_NOT_EXIST
    """

    NO_ERROR                    = auto()
    NOT_CONNECTED               = auto()
    DECODE_ERROR                = auto()
    MALFORMED_JSON              = auto()
    EMPTY_RESPONSE              = auto()
    NOT_A_FILE                  = auto()
    INVALID_QUERY               = auto()
    INVALID_SETUP               = auto()
    HTTP_ERROR                  = auto()
    CONN_TIMEOUT                = auto()
    REQ_TIMEOUT                 = auto()
    SSL_ERROR                   = auto()
    CONN_ERROR                  = auto()
    UNKONWN_EXCPTION            = auto()
    FILE_IO_ERROR               = auto()
    REMOTE_FILE_NOT_FOUND       = auto()
    RESOURCE_DOES_NOT_EXIST     = auto()
    INVALID_CREDENTIALS         = auto()

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

    #TODO implement missing transitions, ensure only the above transitions are
    # allowed

    CONNECTED       = auto()
    CONNECTING      = auto()
    DISCONNECTED    = auto()
    DISCONNECTING   = auto()
    NOT_SETUP       = auto()
    FAILED          = auto()




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