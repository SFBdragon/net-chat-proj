"""
Test the functionality of server.py

Run with:
- uv run src/test_server.py
"""

import asyncio
import socket
import tempfile
import unittest

from pydantic import TypeAdapter

import protocol
from server import Server


def serve() -> Server:
    """
    Create a server for testing purposes. Runs on localhost and uses random available ports.

    Use
    """

    temp_db_file = tempfile.NamedTemporaryFile(
        suffix=".sqlite", mode="w", delete=False, delete_on_close=False
    )

    any_available_port = 0

    sv = Server(temp_db_file.name, "127.0.0.1", any_available_port, any_available_port)
    sv.run()

    temp_db_file.close()

    return sv


class TestServer(unittest.TestCase):
    def tcp_send_and_validate(
        self,
        server: Server,
        request_header: protocol.Request,
        request_body: bytes | None,
        expected_response_header: protocol.Response,
        expected_response_body: bytes | None,
    ):
        request_json = request_header.model_dump_json()
        request_data = request_json.encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", server.tcp_port()))
        sock.send(request_data)
        sock.send(b"\x03")
        if request_body:
            sock.send(request_body)

        stream = protocol.MapStreamBuffer(sock)
        response_header_bytes = asyncio.run(stream.read_header())
        response_header_json = response_header_bytes.decode("utf-8")
        response_header = protocol.parse_response_header(response_header_json)

        self.assertEqual(response_header, expected_response_header)

        if expected_response_body:
            response_body = asyncio.run(stream.read_body(len(expected_response_body)))
            self.assertEqual(response_body, expected_response_body)

        sock.close()

    def register(self, server: Server, user_id: str):
        register = protocol.Register(
            version=protocol.MAP_VER, userID=user_id, serverID="", type="REGISTER"
        )

        response = protocol.GenericResponse(
            version=protocol.MAP_VER,
            serverID=server.server_id,
            status=protocol.STATUS_OK,
        )

        self.tcp_send_and_validate(server, register, None, response, None)

    def test_register(self):
        server = serve()
        self.register(server, "linus_torvalds")
        server.stop()

    def create_group(
        self, server: Server, user_id: str, group_name: str, members: list[str]
    ):
        register = protocol.CreateGroup(
            version=protocol.MAP_VER,
            userID=user_id,
            serverID=server.server_id,
            type="CREATE_GROUP",
            name=group_name,
            members=members,
        )

        response = protocol.GenericResponse(
            version=protocol.MAP_VER,
            serverID=server.server_id,
            status=protocol.STATUS_OK,
        )

        self.tcp_send_and_validate(server, register, None, response, None)

    def test_create_group(self):
        server = serve()
        self.register(server, "donald_knuth")
        self.register(server, "bjarne_stroustrup")
        self.create_group(server, "bjarne_stroustrup", "C/C++ Gang", ["donald_knuth"])
        server.stop()

    def get_all_events(
        self,
        server: Server,
        user_id: str,
        expected_events: list[protocol.Event],
        afterEventID: int | None = None,
    ):
        register = protocol.GetEvents(
            version=protocol.MAP_VER,
            userID=user_id,
            serverID=server.server_id,
            type="GET_EVENTS",
            groupID=None,
            afterEventID=afterEventID,
            beforeEventID=None,
        )

        expected_events_json = TypeAdapter(list[protocol.Event]).dump_json(
            expected_events
        )

        response = protocol.BodyResponse(
            version=protocol.MAP_VER,
            serverID=server.server_id,
            status=protocol.STATUS_OK,
            length=len(expected_events_json),
        )

        self.tcp_send_and_validate(
            server, register, None, response, expected_events_json
        )

    def send_message(self, server: Server, user_id: str, group_id: int, message: str):
        message_body = message.encode("utf-8")

        register = protocol.PutMessage(
            version=protocol.MAP_VER,
            userID=user_id,
            serverID=server.server_id,
            type="PUT_MESSAGE",
            groupID=group_id,
            length=len(message_body),
        )

        response = protocol.GenericResponse(
            version=protocol.MAP_VER,
            serverID=server.server_id,
            status=protocol.STATUS_OK,
        )

        self.tcp_send_and_validate(server, register, message_body, response, None)

    def test_send_message_and_get_events(self):
        server = serve()
        self.register(server, "donald_knuth")
        self.register(server, "bjarne_stroustrup")
        self.create_group(server, "bjarne_stroustrup", "C/C++ Gang", ["donald_knuth"])
        self.get_all_events(
            server,
            "bjarne_stroustrup",
            [
                protocol.AddMemberEvent(
                    eventID=1,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="bjarne_stroustrup",
                ),
                protocol.AddMemberEvent(
                    eventID=2,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="donald_knuth",
                ),
            ],
        )
        self.get_all_events(
            server,
            "donald_knuth",
            [
                protocol.AddMemberEvent(
                    eventID=1,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="bjarne_stroustrup",
                ),
                protocol.AddMemberEvent(
                    eventID=2,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="donald_knuth",
                ),
            ],
        )

        self.send_message(
            server,
            "donald_knuth",
            1,
            "I wrote a cool book!",
        )

        self.get_all_events(
            server,
            "bjarne_stroustrup",
            [
                protocol.AddMemberEvent(
                    eventID=1,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="bjarne_stroustrup",
                ),
                protocol.AddMemberEvent(
                    eventID=2,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="donald_knuth",
                ),
                protocol.MessageEvent(
                    eventID=3,
                    groupID=1,
                    senderUserID="donald_knuth",
                    type="SEND_MESSAGE",
                    message="I wrote a cool book!",
                ),
            ],
        )
        self.get_all_events(
            server,
            "donald_knuth",
            [
                protocol.AddMemberEvent(
                    eventID=2,
                    groupID=1,
                    senderUserID="bjarne_stroustrup",
                    type="ADD_MEMBER",
                    groupName="C/C++ Gang",
                    userID="donald_knuth",
                ),
                protocol.MessageEvent(
                    eventID=3,
                    groupID=1,
                    senderUserID="donald_knuth",
                    type="SEND_MESSAGE",
                    message="I wrote a cool book!",
                ),
            ],
            afterEventID=1,
        )
        server.stop()

    def im_alive(
        self,
        server: Server,
        user_id: str,
        local_ip: str,
        expected_outdated: bool,
        after_event_id: int | None = None,
    ):
        request = protocol.ImAlive(
            version=protocol.MAP_VER,
            userID=user_id,
            serverID=server.server_id,
            type="IM_ALIVE",
            localIP=local_ip,
            afterEventID=after_event_id,
        )
        request_json = request.model_dump_json()
        request_data = request_json.encode("utf-8") + b"\x03"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(request_data, ("127.0.0.1", server.udp_port()))

        expected_response = protocol.ImAliveResponse(
            version=protocol.MAP_VER,
            serverID=server.server_id,
            status=protocol.STATUS_OK,
            isOutdated=expected_outdated,
        )

        print("PRE_RECEIVE")
        response, _ = sock.recvfrom(65535)
        print("POST_RECEIVE")
        response_header_json = response.decode("utf-8").rstrip("\x03")
        response_header = protocol.parse_response_header(response_header_json)

        self.assertEqual(response_header, expected_response)

        sock.close()

    def test_im_alive(self):
        server = serve()
        self.register(server, "donald_knuth")
        self.register(server, "bjarne_stroustrup")
        self.im_alive(server, "donald_knuth", "Donald's IP", False)
        self.im_alive(server, "bjarne_stroustrup", "Bjarne's IP", False)
        server.stop()

    def get_peer(
        self,
        server: Server,
        user_id: str,
        group_id: int,
        peer_user_id: str,
        expected_peer_user_id: str,
    ):
        register = protocol.GetPeer(
            version=protocol.MAP_VER,
            userID=user_id,
            serverID=server.server_id,
            type="GET_PEER",
            groupID=group_id,
            peerUserID=peer_user_id,
        )

        expected_body = expected_peer_user_id.encode("utf-8")
        response = protocol.BodyResponse(
            version=protocol.MAP_VER,
            serverID=server.server_id,
            status=protocol.STATUS_OK,
            length=len(expected_body),
        )

        self.tcp_send_and_validate(server, register, None, response, expected_body)

    def test_get_peer(self):
        server = serve()
        self.register(server, "donald_knuth")
        self.register(server, "bjarne_stroustrup")
        self.create_group(server, "donald_knuth", "C/C++ Gang", ["bjarne_stroustrup"])
        self.im_alive(server, "donald_knuth", "Donald's IP", True)
        self.im_alive(server, "bjarne_stroustrup", "Bjarne's IP", True)
        self.get_peer(server, "bjarne_stroustrup", 1, "donald_knuth", "Donald's IP")
        self.get_peer(server, "donald_knuth", 1, "bjarne_stroustrup", "Bjarne's IP")
        server.stop()


if __name__ == "__main__":
    unittest.main()
