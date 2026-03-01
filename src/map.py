"""
MAP: Messaging Application-layer Protocol

This file provides functions, types, and utilities for working with MAP data.
"""

from typing import Literal, Optional

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
    user_id: str = Field(alias="userID")
    server_id: str = Field(alias="serverID")


class ImAlive(BaseRequest):
    type: Literal["IM_ALIVE"]
    local_ip: str = Field(alias="localIP")
    after_event_id: Optional[int] = Field(alias="afterEventID")


class Register(BaseRequest):
    type: Literal["REGISTER"]


class CreateGroup(BaseRequest):
    type: Literal["CREATE_GROUP"]
    name: str
    members: list[str]


class PutMessage(BaseRequest):
    type: Literal["PUT_MESSAGE"]
    group_id: int = Field(alias="groupID")
    length: int


class PutFile(BaseRequest):
    type: Literal["PUT_FILE"]
    group_id: int = Field(alias="groupID")
    file_name: str = Field(alias="fileName")
    sha256: str


class PutMember(BaseRequest):
    type: Literal["PUT_MEMBER"]
    group_id: int = Field(alias="groupID")
    add_user_id: str = Field(alias="addUserID")


class GetEvents(BaseRequest):
    type: Literal["GET_EVENTS"]
    group_id: Optional[int] = Field(alias="groupID")
    after_event_id: Optional[int] = Field(alias="afterEventID")
    before_event_id: Optional[int] = Field(alias="beforeEventID")


class GetAlive(BaseRequest):
    type: Literal["GET_ALIVE"]
    group_id: int = Field(alias="groupID")


class GetPeer(BaseRequest):
    type: Literal["GET_PEER"]
    group_id: int = Field(alias="groupID")
    peer_user_id: str = Field(alias="peerUserID")


class FileRequest(BaseRequest):
    type: Literal["FILE_REQUEST"]
    group_id: int = Field(alias="groupID")
    sha256: str


Request = (
    ImAlive
    | Register
    | CreateGroup
    | PutMessage
    | PutFile
    | PutMember
    | GetEvents
    | GetAlive
    | GetPeer
    | FileRequest
)


class GenericResponse(BaseModel):
    version: str
    server_id: str = Field(alias="serverID")
    status: str


class ImAliveResponse(GenericResponse):
    is_outdated: bool = Field(alias="isOutdated")


class FileRequestResponse(GenericResponse):
    length: int


Response = GenericResponse | ImAliveResponse | FileRequestResponse
