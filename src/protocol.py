"""
MAP: Messaging Application-layer Protocol

This file provides functions, types, and utilities for working with MAP data.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

SERVER_TCP_PORT = 3030
SERVER_UDP_PORT = 3031

MAP_VER = "1.0"

HEADER_BODY_DELIMITER = b"\x03"

STATUS_OK = "OK"
STATUS_BAD_REQUEST = "BAD_REQUEST"
STATUS_MISSING_FIELD = "MISSING_FIELD"
STATUS_INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
STATUS_UNKNOWN_SERVER = "UNKNOWN_SERVER"
STATUS_UNKNOWN_USER = "UNKNOWN_USER"
STATUS_FILE_UNAVAILABLE = "FILE_UNAVAILABLE"
STATUS_NOT_MEMBER = "NOT_MEMBER"


class MapStreamBuffer:
    """
    A buffer that allows for parsing a TCP stream as MAP header and body segments.

    This assumed the following is guaranteed by MAP:
    - All headers end in `HEADER_BODY_DELIMITER`
    - All headers indicate the length of their body.

    This is not request or response-specific.
    """

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = bytearray()

    async def _recv_into_buffer(self, size=4096):
        """Receive data and append to buffer."""

        loop = asyncio.get_event_loop()

        data = await loop.sock_recv(self.sock, size)
        if not data:
            raise ConnectionError("Socket closed")
        self.buffer.extend(data)

    async def read_header(self) -> bytes:
        """Read and consume bytes until delimiter is found."""
        while True:
            try:
                idx = self.buffer.index(HEADER_BODY_DELIMITER)
                result = bytes(self.buffer[:idx])
                del self.buffer[: idx + 1]  # consume including delimiter
                return result
            except ValueError:
                # delimiter not found, need more data
                await self._recv_into_buffer()

    async def read_body(self, size: int) -> bytes:
        """Read exactly n bytes."""
        while len(self.buffer) < size:
            await self._recv_into_buffer()

        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result


class Status(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def check_versions_match(supported: str, received: str):

    suppported_split = supported.split(".", 1)
    if len(suppported_split) != 2:
        raise Exception("Invalid supposed version. Must be `MAJOR.MINOR`")

    received_split = received.split(".", 1)
    if len(received_split) != 2:
        raise Status(STATUS_BAD_REQUEST)

    supported_major = int(suppported_split[0])
    _supported_minor = int(suppported_split[1])

    try:
        received_major = int(received_split[0])
        _received_minor = int(received_split[1])
    except ValueError:
        raise Status(STATUS_BAD_REQUEST)

    if supported_major != received_major:
        raise Status(STATUS_INCOMPATIBLE_VERSION)


def parse_request_header(header_bytes: bytes, expected_server_id: str) -> Request:
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

    # Raises a Status exception if the received request's version is
    # poorly formatted or incompatbile with this MAP implementation (1.0).
    check_versions_match(MAP_VER, header.version)

    # Raise a Status exception if the server_id field doesn't match the
    if header.serverID != expected_server_id and not (
        header.type == "REGISTER" and not header.serverID and not header.type == "FILE_REQUEST"
    ):
        raise Status(STATUS_UNKNOWN_SERVER)

    return header


def parse_response_header(json_str: str) -> Response:
    return TypeAdapter(Response).validate_json(json_str)


def parse_events_response_body(json_str: str) -> list[Event]:
    return TypeAdapter(list[Event]).validate_json(json_str)


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


class BaseEvent(BaseModel):
    eventID: int
    groupID: int
    senderUserID: str


class MessageEvent(BaseEvent):
    type: Literal["SEND_MESSAGE"]
    message: str


class FileAvailableEvent(BaseEvent):
    type: Literal["FILE_AVAILABLE"]
    sha256: str
    fileName: str


class AddMemberEvent(BaseEvent):
    type: Literal["ADD_MEMBER"]
    userID: str
    groupName: str


Event = Annotated[
    MessageEvent | FileAvailableEvent | AddMemberEvent,
    Field(discriminator="type"),
]
