from enum import IntEnum


class JobStatus(IntEnum):
    QUEUED = 1
    RUNNING = 2
    READY = 3
    FAILED = 4
    SUCCESSFUL = 5
    ABORTED = 6
    MARKED_FOR_DELETION = 7


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
    r"""
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
