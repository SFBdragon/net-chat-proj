import asyncio
import socket
import threading
import time

from pydantic import TypeAdapter

import db as database
import protocol
from utils import run_async_in_thread

LIVENESS_TIMEOUT = 5.0


class Server:
    def __init__(self, db_path: str, host: str, tcp_port: int, udp_port: int):
        self.server_id = database.init_db(db_path)
        self._db_path = db_path

        # Map of UserIDs to
        # 1. Time since epoch of last IM_ALIVE
        #   - Needed to track liveness
        # 2. The client's IP on its LAN
        #   - Necessary for facilitating client P2P networking
        self._user_liveness: dict[str, tuple[float, str]] = {}
        # Synchronize motifications to the user liveness dict.
        self._user_liveness_lock = threading.RLock()

        # Bind both ports upfront.
        # Save the ports that were bound in case we bound to port 0 (any available port)
        # which is useful for testing.

        self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_socket.bind((host, tcp_port))
        self._tcp_socket.setblocking(False)

        _, tcp_port = self._tcp_socket.getsockname()
        print(f"TCP socket bound on {host}:{tcp_port}")

        self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_socket.bind((host, udp_port))
        self._udp_socket.setblocking(False)

        _, udp_port = self._udp_socket.getsockname()
        print(f"UDP socket bound on {host}:{udp_port}")

        self._shutdown = False
        self._tcp_thread: threading.Thread | None = None
        self._udp_thread: threading.Thread | None = None

    def tcp_port(self) -> int:
        """Get the TCP port the server is listening on."""
        _, port = self._tcp_socket.getsockname()
        return port

    def udp_port(self) -> int:
        """Get the UDP port the server is listening on."""
        _, port = self._udp_socket.getsockname()
        return port

    def run(self):
        """
        Start the TCP and UDP listening and request handling threads.

        Use `.stop()` to stop the server listening for requests.
        """

        assert self._tcp_thread is None
        assert self._udp_thread is None

        self._tcp_socket.listen(10)

        self._tcp_thread = run_async_in_thread(self._tcp_server())
        self._udp_thread = run_async_in_thread(self._udp_server())

    def stop(self):
        """
        Stop the server listening threads.

        This leaves the sockets bound. It's possible to run() the server again after calling stop().
        """

        assert self._tcp_thread is not None
        assert self._udp_thread is not None

        self._shutdown = True

        print("Closing sockets...")

        # Unblock pending receives
        self._tcp_socket.shutdown(socket.SHUT_RD)

        # UDP recvfrom blocks and there's no particularly clean way to get
        # it to unblock (possible: sending oneself data, closing socket +
        # cancelling task sometimes works as intended, but not always).
        # So recvfrom just times out regularly and checks _shutdown.
        # We set it to True above

        print("Joining threads...")

        self._tcp_thread.join()
        self._udp_thread.join()

        self._shutdown = False
        self._tcp_thread = None
        self._udp_thread = None

    async def _udp_server(self):
        """Run the UDP listening and request handling loop."""

        async with database.Database(self._db_path) as db:
            addr, port = self._udp_socket.getsockname()
            print(f"UDP receiving on {addr}:{port}")

            loop = asyncio.get_event_loop()
            while not self._shutdown:
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(self._udp_socket, 65535), timeout=0.1
                    )
                    asyncio.create_task(self._handle_udp_request(data, addr, db))
                except asyncio.TimeoutError:
                    continue

        print("UDP server stopped...")

    async def _handle_udp_request(
        self, data: bytes, addr, db: database.DatabaseConnection
    ):
        """
        Handle a single UDP request.

        :param data: The bytes within the datagram.
        :param addr: The IP of the datagram sender.
        :param db: The database connection for the current thread's async context.
        """

        loop = asyncio.get_event_loop()

        print(f"> UDP received from {addr}: {data}")

        try:
            header = protocol.parse_request_header(data.rstrip(b"\x03"), self.server_id)

            # Only IM_ALIVE requests should arrive on UDP.
            if not isinstance(header, protocol.ImAlive):
                raise protocol.Status(protocol.STATUS_BAD_REQUEST)

            with self._user_liveness_lock:
                self._user_liveness[header.userID] = time.time(), header.localIP

            events = await db.get_events(
                header.userID, None, header.afterEventID or 0, None
            )

            updated = False
            if events:
                if events:
                    updated = True

            response = protocol.ImAliveResponse(
                version=protocol.MAP_VER,
                serverID=self.server_id,
                status=protocol.STATUS_OK,
                isOutdated=updated,
            )
        except protocol.Status as s:
            response = protocol.GenericResponse(
                version=protocol.MAP_VER, serverID=self.server_id, status=s.status
            )

        response_json_str = response.model_dump_json()

        print(f"< UDP sending to {addr}: {response_json_str}")

        response_bytes = response_json_str.encode("utf-8") + b"\x03"
        await loop.sock_sendto(self._udp_socket, response_bytes, addr)

    async def _tcp_server(self):
        """Run the TCP listening and request handling loop."""

        async with database.Database(self._db_path) as db:
            addr, port = self._tcp_socket.getsockname()
            print(f"TCP listening on {addr}:{port}")

            loop = asyncio.get_event_loop()
            try:
                while not self._shutdown:
                    client_sock, addr = await loop.sock_accept(self._tcp_socket)
                    asyncio.create_task(self._handle_tcp_client(client_sock, addr, db))
            except OSError:
                # Socket shutdown
                pass

        print("TCP server stopped...")

    async def _handle_tcp_client(
        self, sock: socket.socket, addr, db: database.DatabaseConnection
    ):
        """
        Handle a TCP client connection.

        :param sock: The connection we have with the client.
        :param db: The database connection held by the current thread's async context.
        """

        print(f"TCP connection from {addr}")

        loop = asyncio.get_event_loop()

        try:
            stream = protocol.MapStreamBuffer(sock)

            while True:
                header_bytes = await stream.read_header()
                print(f"> TCP received from {addr}: {header_bytes}")

                response_body = None

                try:
                    header = protocol.parse_request_header(header_bytes, self.server_id)

                    match header:
                        case protocol.Register():
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=self.server_id,
                                status=protocol.STATUS_OK,
                            )
                        case protocol.CreateGroup():
                            group_id = await db.create_group(header.name)

                            await db.create_membership(group_id, header.userID)
                            await db.create_event(
                                group_id,
                                header.userID,
                                header.userID,
                                database.EVENT_TYPE_ADD_MEMBER,
                            )

                            for member in header.members:
                                await db.create_membership(group_id, member)
                                await db.create_event(
                                    group_id,
                                    header.userID,
                                    member,
                                    database.EVENT_TYPE_ADD_MEMBER,
                                )

                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=self.server_id,
                                status=protocol.STATUS_OK,
                            )
                        case protocol.PutMessage():
                            if not await db.check_membership(
                                header.userID, header.groupID
                            ):
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_NOT_MEMBER,
                                )
                            else:
                                message = await stream.read_body(header.length)

                                try:
                                    message = message.decode("utf-8")
                                except UnicodeDecodeError:
                                    raise protocol.Status(protocol.STATUS_BAD_REQUEST)

                                await db.create_event(
                                    header.groupID,
                                    header.userID,
                                    message,
                                    database.EVENT_TYPE_MESSAGE,
                                )

                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_OK,
                                )
                        case protocol.PutFile():
                            if not await db.check_membership(
                                header.userID, header.groupID
                            ):
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_NOT_MEMBER,
                                )
                            else:
                                data = database.FileAvailabilityEventData(
                                    name=header.fileName, sha256=header.sha256
                                )
                                json_data = data.model_dump_json()

                                await db.create_event(
                                    header.groupID,
                                    header.userID,
                                    json_data,
                                    database.EVENT_TYPE_FILE_AVAILABILITY,
                                )

                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_OK,
                                )
                        case protocol.PutMember():
                            if not await db.check_membership(
                                header.userID, header.groupID
                            ):
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_NOT_MEMBER,
                                )
                            else:
                                await db.create_membership(
                                    header.groupID, header.addUserID
                                )

                                await db.create_event(
                                    header.groupID,
                                    header.userID,
                                    header.addUserID,
                                    database.EVENT_TYPE_ADD_MEMBER,
                                )

                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_OK,
                                )
                        case protocol.GetPeer():
                            if not await db.check_membership(
                                header.userID, header.groupID
                            ):
                                raise protocol.Status(protocol.STATUS_NOT_MEMBER)

                            if not await db.check_membership(
                                header.peerUserID, header.groupID
                            ):
                                raise protocol.Status(protocol.STATUS_NOT_MEMBER)

                            try:
                                with self._user_liveness_lock:
                                    t, ip = self._user_liveness[header.peerUserID]
                            except KeyError:
                                raise protocol.Status(protocol.STATUS_UNKNOWN_USER)

                            if time.time() - LIVENESS_TIMEOUT < t:
                                response_body = ip.encode("utf-8")
                                response_header = protocol.BodyResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_OK,
                                    length=len(response_body),
                                )
                            else:
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_FILE_UNAVAILABLE,
                                )
                        case protocol.GetEvents():
                            if header.groupID:
                                if not await db.check_membership(
                                    header.userID, header.groupID
                                ):
                                    response_header = protocol.GenericResponse(
                                        version=protocol.MAP_VER,
                                        serverID=self.server_id,
                                        status=protocol.STATUS_NOT_MEMBER,
                                    )

                            events = await db.get_events(
                                header.userID,
                                header.groupID,
                                header.afterEventID or 0,
                                header.beforeEventID,
                            )

                            response_body = (
                                TypeAdapter(list[protocol.Event]).dump_json(
                                    list(events)
                                )
                                if events
                                else b"[]"
                            )
                            response_header = protocol.BodyResponse(
                                version=protocol.MAP_VER,
                                serverID=self.server_id,
                                status=protocol.STATUS_OK,
                                length=len(response_body),
                            )
                        case protocol.GetAlive():
                            if not await db.check_membership(
                                header.userID, header.groupID
                            ):
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_NOT_MEMBER,
                                )
                            else:
                                members = await db.group_members(header.groupID)

                                if members:
                                    t = time.time()
                                    with self._user_liveness_lock:
                                        members = filter(
                                            lambda member: (
                                                self._user_liveness[member][0]
                                                > t - LIVENESS_TIMEOUT
                                            ),
                                            members,
                                        )
                                    members = list(members)
                                else:
                                    members = []

                                response_body = TypeAdapter(list[str]).dump_json(
                                    members
                                )
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=self.server_id,
                                    status=protocol.STATUS_OK,
                                )
                        case _:
                            print(f"TODO handle {type(header)}")
                            return

                except protocol.Status as s:
                    response_header = protocol.GenericResponse(
                        version=protocol.MAP_VER,
                        serverID=self.server_id,
                        status=s.status,
                    )

                response_json = response_header.model_dump_json()
                response_bytes = response_json.encode("utf-8")

                print(f"< TCP sending to {addr}: {response_json}\x03")
                await loop.sock_sendall(sock, response_bytes)
                await loop.sock_sendall(sock, b"\x03")

                if response_body:
                    print(f"< TCP sending to {addr}: {response_body}")
                    await loop.sock_sendall(sock, response_body)
        except ConnectionError as _:
            pass
        finally:
            sock.close()
            print(f"TCP closed: {addr}")


if __name__ == "__main__":
    server = Server("database.sqlite3", "0.0.0.0", 3030, 3031)
    server.run()

    while True:
        pass
