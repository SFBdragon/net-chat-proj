import asyncio
import socket
import threading
import time

import db
import map

SERVER_IP = "0.0.0.0"
SERVER_TCP_PORT = 3030
SERVER_UDP_PORT = 3031

MAP_VER = "1.0"
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
        stream = map.MapStreamBuffer(sock)

        while True:
            header_bytes = await stream.read_header()
            print(f"> TCP received from {addr}: {header_bytes}")

            response_body = None

            try:
                header = map.parse_request_header(header_bytes)

                if header.serverID != SERVER_ID:
                    raise map.Status(map.STATUS_UNKNOWN_SERVER)

                match header:
                    case map.Register():
                        # TODO
                        pass
                    case map.GetPeer():
                        # TODO validate that peerUserID and userID are in groupID

                        try:
                            t, ip = user_liveness[header.peerUserID]
                        except KeyError:
                            raise map.Status(map.STATUS_UNKNOWN_USER)

                        if time.time() - LIVENESS_TIMEOUT < t:
                            response_body = ip.encode("utf-8")
                            response_header = map.BodyResponse(
                                version=MAP_VER,
                                serverID=SERVER_ID,
                                status=map.STATUS_OK,
                                length=len(response_body),
                            )
                        else:
                            response_header = map.GenericResponse(
                                version=MAP_VER,
                                serverID=SERVER_ID,
                                status=map.STATUS_FILE_UNAVAILABLE,
                            )
                    case _:
                        print(f"TODO handle {type(header)}")
                        return

            except map.Status as s:
                response_header = map.GenericResponse(
                    version=MAP_VER, serverID=SERVER_ID, status=s.status
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
        header = map.parse_request_header(data)

        if header.serverID != SERVER_ID:
            raise map.Status(map.STATUS_UNKNOWN_SERVER)

        # Only IM_ALIVE requests should arrive on UDP.
        if not isinstance(header, map.ImAlive):
            raise map.Status(map.STATUS_BAD_REQUEST)

        # TODO validate userID
        # TODO check if outdated

        user_liveness[header.userID] = time.time(), header.localIP

        response = map.ImAliveResponse(
            version=MAP_VER, serverID=SERVER_ID, status=map.STATUS_OK, isOutdated=True
        )
    except map.Status as s:
        response = map.GenericResponse(
            version=MAP_VER, serverID=SERVER_ID, status=s.status
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

    # TODO set the SERVER_ID

    tcp_thread = run_async_in_thread(tcp_server_raw(SERVER_IP, SERVER_TCP_PORT))
    udp_thread = run_async_in_thread(udp_server_raw(SERVER_IP, SERVER_UDP_PORT))

    while True:
        pass
