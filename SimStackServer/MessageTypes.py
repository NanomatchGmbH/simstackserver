from enum import IntEnum, auto

import msgpack
#Alias here to be able to switch to json
mypacker = msgpack

class InvalidMessageError(Exception):
    pass

class SSS_MESSAGETYPE(IntEnum):
    CONNECT = auto()
    LISTWFS = auto()
    LISTJOBS = auto()
    DELWF = auto()
    ABORTWF = auto()
    ABORTJOB = auto()
    DELJOB = auto()
    DISCONNECT = auto()


class Message(object):
    @classmethod
    def connect_message(cls):
        mydict = {"MessageType": SSS_MESSAGETYPE.CONNECT}
        return mypacker.dumps(mydict)

    """The two next functions exist in case we need to fumble with encoding."""
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

