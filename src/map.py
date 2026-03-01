"""
MAP: Messaging Application-layer Protocol

This file provides functions, types, and utilities for working with MAP data.
"""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

HEADER_BODY_DELIMITER = b"\x03"


def split_header_and_body(data: bytes) -> tuple[bytes, Optional[bytes]]:
    if HEADER_BODY_DELIMITER in data:
        header, body = data.split(HEADER_BODY_DELIMITER, 1)
        return (header, body)
    else:
        return (data, None)


def decode_header(header: bytes) -> str:
    """
    Attempt to decode the header as UTF-8.

    Errors: `UnicodeDecodeError`
    """

    return header.decode("utf-8")


def parse_request_header(json_str: str) -> Request:
    return TypeAdapter(Request).validate_json(json_str)


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


class FileRequestResponse(GenericResponse):
    length: int


Response = GenericResponse | ImAliveResponse | FileRequestResponse
