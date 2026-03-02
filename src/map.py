"""
MAP: Messaging Application-layer Protocol

This file provides functions, types, and utilities for working with MAP data.
"""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

HEADER_BODY_DELIMITER = b"\x03"

STATUS_OK = "OK"
STATUS_BAD_REQUEST = "BAD_REQUEST"
STATUS_MISSING_FIELD = "MISSING_FIELD"
STATUS_INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
STATUS_UNKNOWN_SERVER = "UNKNOWN_SERVER"
STATUS_UNKNOWN_USER = "UNKNOWN_USER"
STATUS_FILE_UNAVAILABLE = "FILE_UNAVAILABLE"


def split_header_and_body(data: bytes) -> tuple[bytes, Optional[bytes]]:
    if HEADER_BODY_DELIMITER in data:
        header, body = data.split(HEADER_BODY_DELIMITER, 1)
        return (header, body)
    else:
        return (data, None)


class Status(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def parse_request_header(header_bytes: bytes) -> Request:
    try:
        header_json = header_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise Status(STATUS_BAD_REQUEST)

    try:
        header: Request = TypeAdapter(Request).validate_json(header_json)
    except ValidationError as ve:
        for error in ve.errors():
            if error["type"] == "missing":
                print(str(error))
                raise Status(STATUS_MISSING_FIELD)
            elif error["type"] == "extra_forbidden":
                # TODO extra field error?
                raise Status(STATUS_BAD_REQUEST)
            else:
                print(str(error))
                exit(1)

        raise Status(STATUS_BAD_REQUEST)

    return header


def parse_response_header(json_str: str) -> Response:
    return TypeAdapter(Response).validate_json(json_str)


class BaseRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    version: str
    userID: str
    serverID: str


class ImAlive(BaseRequest):
    type: Literal["IM_ALIVE"]
    localIP: str
    afterEventID: Optional[int]


class Register(BaseRequest):
    type: Literal["REGISTER"]


class CreateGroup(BaseRequest):
    type: Literal["CREATE_GROUP"]
    name: str
    members: list[str]


class PutMessage(BaseRequest):
    type: Literal["PUT_MESSAGE"]
    groupID: int
    length: int


class PutFile(BaseRequest):
    type: Literal["PUT_FILE"]
    groupID: int
    fileName: str
    sha256: str


class PutMember(BaseRequest):
    type: Literal["PUT_MEMBER"]
    groupID: int
    addUserID: str


class GetEvents(BaseRequest):
    type: Literal["GET_EVENTS"]
    groupID: Optional[int]
    afterEventID: Optional[int]
    beforeEventID: Optional[int]


class GetAlive(BaseRequest):
    type: Literal["GET_ALIVE"]
    groupID: int


class GetPeer(BaseRequest):
    type: Literal["GET_PEER"]
    groupID: int
    peerUserID: str


class FileRequest(BaseRequest):
    type: Literal["FILE_REQUEST"]
    groupID: int
    sha256: str


Request = Annotated[
    ImAlive
    | Register
    | CreateGroup
    | PutMessage
    | PutFile
    | PutMember
    | GetEvents
    | GetAlive
    | GetPeer
    | FileRequest,
    Field(discriminator="type"),
]


class GenericResponse(BaseModel):
    version: str
    serverID: str
    status: str


class ImAliveResponse(GenericResponse):
    isOutdated: bool


class BodyResponse(GenericResponse):
    length: int


Response = GenericResponse | ImAliveResponse | BodyResponse
