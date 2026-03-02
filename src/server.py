import asyncio
import socket
import threading
import time

from pydantic import TypeAdapter

import db
import protocol

SERVER_IP = "0.0.0.0"

SERVER_ID = ""

LIVENESS_TIMEOUT = 5.0

# Map of UserIDs to
# 1. Time since epoch of last IM_ALIVE
#   - Needed to track liveness
# 2. The client's IP on its LAN
#   - Necessary for initiating P2P
user_liveness: dict[str, tuple[float, str]] = {}


async def handle_tcp_client(sock, addr):
    """Handle a TCP client connection."""

    print(f"TCP connection from {addr}")

    loop = asyncio.get_event_loop()

    try:
        stream = protocol.MapStreamBuffer(sock)

        while True:
            header_bytes = await stream.read_header()
            print(f"> TCP received from {addr}: {header_bytes}")

            response_body = None

            try:
                header = protocol.parse_request_header(header_bytes, SERVER_ID)

                match header:
                    case protocol.Register():
                        response_header = protocol.GenericResponse(
                            version=protocol.MAP_VER,
                            serverID=SERVER_ID,
                            status=protocol.STATUS_OK,
                        )
                    case protocol.CreateGroup():
                        group_id = await db.create_group(header.name)

                        await db.create_membership(group_id, header.userID)

                        for member in header.members:
                            await db.create_membership(group_id, member)
                            await db.create_event(
                                group_id,
                                header.userID,
                                member,
                                db.EVENT_TYPE_ADD_MEMBER,
                            )

                        response_header = protocol.GenericResponse(
                            version=protocol.MAP_VER,
                            serverID=SERVER_ID,
                            status=protocol.STATUS_OK,
                        )
                    case protocol.PutMessage():
                        if not db.check_membership(header.userID, header.groupID):
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
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
                                db.EVENT_TYPE_MESSAGE,
                            )

                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_OK,
                            )
                    case protocol.PutFile():
                        if not db.check_membership(header.userID, header.groupID):
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_NOT_MEMBER,
                            )
                        else:
                            data = db.FileAvailabilityEventData(
                                name=header.fileName, sha256=header.sha256
                            )
                            json_data = data.model_dump_json()

                            await db.create_event(
                                header.groupID,
                                header.userID,
                                json_data,
                                db.EVENT_TYPE_FILE_AVAILABILITY,
                            )

                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_OK,
                            )
                    case protocol.PutMember():
                        if not db.check_membership(header.userID, header.groupID):
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_NOT_MEMBER,
                            )
                        else:
                            await db.create_event(
                                header.groupID,
                                header.userID,
                                header.addUserID,
                                db.EVENT_TYPE_ADD_MEMBER,
                            )

                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_OK,
                            )
                    case protocol.GetPeer():
                        # TODO validate that peerUserID and userID are in groupID

                        try:
                            t, ip = user_liveness[header.peerUserID]
                        except KeyError:
                            raise protocol.Status(protocol.STATUS_UNKNOWN_USER)

                        if time.time() - LIVENESS_TIMEOUT < t:
                            response_body = ip.encode("utf-8")
                            response_header = protocol.BodyResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_OK,
                                length=len(response_body),
                            )
                        else:
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_FILE_UNAVAILABLE,
                            )
                    case protocol.GetEvents():
                        if header.groupID:
                            if not db.check_membership(header.userID, header.groupID):
                                response_header = protocol.GenericResponse(
                                    version=protocol.MAP_VER,
                                    serverID=SERVER_ID,
                                    status=protocol.STATUS_NOT_MEMBER,
                                )

                        events = await db.get_events(
                            header.userID,
                            header.groupID,
                            header.afterEventID,
                            header.beforeEventID,
                        )

                        response_body = (
                            TypeAdapter(list[protocol.Event]).dump_json(list(events))
                            if events
                            else b""
                        )
                        response_header = protocol.BodyResponse(
                            version=protocol.MAP_VER,
                            serverID=SERVER_ID,
                            status=protocol.STATUS_OK,
                            length=len(response_body),
                        )
                    case protocol.GetAlive():
                        if not db.check_membership(header.userID, header.groupID):
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_NOT_MEMBER,
                            )
                        else:
                            members = await db.group_members(header.groupID)

                            if members:
                                t = time.time()
                                members = filter(
                                    lambda member: (
                                        user_liveness[member][0] > t - LIVENESS_TIMEOUT
                                    ),
                                    members,
                                )
                                members = list(members)
                            else:
                                members = []

                            response_body = TypeAdapter(list[str]).dump_json(members)
                            response_header = protocol.GenericResponse(
                                version=protocol.MAP_VER,
                                serverID=SERVER_ID,
                                status=protocol.STATUS_OK,
                            )
                    case _:
                        print(f"TODO handle {type(header)}")
                        return

            except protocol.Status as s:
                response_header = protocol.GenericResponse(
                    version=protocol.MAP_VER, serverID=SERVER_ID, status=s.status
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


async def tcp_server_raw(host: str, port: int):
    """Raw TCP server using sock_* methods."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(10)
        server.setblocking(False)

        loop = asyncio.get_event_loop()

        print(f"TCP server listening on {host}:{port}")

        while True:
            client_sock, addr = await loop.sock_accept(server)
            asyncio.create_task(handle_tcp_client(client_sock, addr))


async def handle_udp_request(sock, data, addr, loop):
    """Handle a single UDP request."""

    print(f"> UDP received from {addr}: {data}")

    try:
        header = protocol.parse_request_header(data, SERVER_ID)

        # Only IM_ALIVE requests should arrive on UDP.
        if not isinstance(header, protocol.ImAlive):
            raise protocol.Status(protocol.STATUS_BAD_REQUEST)

        # TODO validate userID
        # TODO check if outdated

        user_liveness[header.userID] = time.time(), header.localIP

        response = protocol.ImAliveResponse(
            version=protocol.MAP_VER,
            serverID=SERVER_ID,
            status=protocol.STATUS_OK,
            isOutdated=True,
        )
    except protocol.Status as s:
        response = protocol.GenericResponse(
            version=protocol.MAP_VER, serverID=SERVER_ID, status=s.status
        )

    response_json_str = response.model_dump_json()

    print(f"< UDP sending to {addr}: {response_json_str}")

    response_bytes = response_json_str.encode("utf-8")
    await loop.sock_sendto(sock, response_bytes, addr)


async def udp_server_raw(host: str, port: int):
    """Raw UDP server using sock_* methods."""

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        sock.setblocking(False)

        loop = asyncio.get_event_loop()

        print(f"UDP server listening on {host}:{port}")

        while True:
            data, addr = await loop.sock_recvfrom(sock, 65535)
            asyncio.create_task(handle_udp_request(sock, data, addr, loop))


# Entry point for threading
def run_async_in_thread(target_coroutine):
    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(target_coroutine)
        finally:
            loop.close()

    thread = threading.Thread(target=thread_target)
    thread.daemon = True
    thread.start()
    return thread


if __name__ == "__main__":
    import threading

    SERVER_ID = asyncio.run(db.init_db())

    print(f"Database established. Server ID: {SERVER_ID}")

    tcp_thread = run_async_in_thread(
        tcp_server_raw(SERVER_IP, protocol.SERVER_TCP_PORT)
    )
    udp_thread = run_async_in_thread(
        udp_server_raw(SERVER_IP, protocol.SERVER_UDP_PORT)
    )

    while True:
        pass
