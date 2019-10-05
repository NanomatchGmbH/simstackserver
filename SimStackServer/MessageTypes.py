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

class SSS_MESSAGETYPE(IntEnum):
    CONNECT = auto()
    ACK = auto()
    LISTWFS = auto()
    LISTWFSREPLY = auto()
    LISTJOBS = auto()
    LISTJOBSREPLY = auto()
    DELWF = auto()
    ABORTWF = auto()
    ABORTJOB = auto()
    DELJOB = auto()
    DISCONNECT = auto()
    SUBMITWF = auto()

class Message(object):
    @classmethod
    def connect_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.CONNECT}
        return mypacker.dumps(mydict)

    @classmethod
    def ack_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.ACK}
        return mypacker.dumps(mydict)

    """
        The two next functions exist in case we need to fumble with encoding.
        ... which turned out to be true
    """
    @staticmethod
    def _loads(message):
        return mypacker.loads(message, raw = False)

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
