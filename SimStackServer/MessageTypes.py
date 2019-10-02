from enum import IntEnum, auto


class SSS_MESSAGETYPE(IntEnum):
    CONNECT = auto()
    LISTWFS = auto()
    LISTJOBS = auto()
    DELWF = auto()
    ABORTWF = auto()
    ABORTJOB = auto()
    DELJOB = auto()
    DISCONNECT = auto()

