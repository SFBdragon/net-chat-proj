import asyncio
import socket
import threading

import db

SERVER_IP = "0.0.0.0"
SERVER_TCP_PORT = 3030
SERVER_UDP_PORT = 3031

SERVER_ID = ""

# Map of UserIDs to time since
alive_users: dict[str, float] = {}


async def tcp_server_raw(host, port):
    """Raw TCP server using sock_* methods."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(5)
    sock.setblocking(False)

    loop = asyncio.get_event_loop()

    print(f"TCP server listening on {host}:{port}")

    while True:
        client_sock, addr = await loop.sock_accept(sock)
        print(f"TCP connection from {addr}")
        asyncio.create_task(handle_tcp_client(client_sock, addr))


async def handle_tcp_client(sock, addr):
    """Handle a TCP client connection."""
    loop = asyncio.get_event_loop()

    try:
        while True:
            data = await loop.sock_recv(sock, 1024)
            if not data:
                break
            print(f"TCP received: {data}")
            await loop.sock_sendall(sock, data)  # Echo
    finally:
        sock.close()
        print(f"TCP closed: {addr}")


async def udp_server_raw(host, port):
    """Raw UDP server using sock_* methods."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.setblocking(False)

    loop = asyncio.get_event_loop()

    print(f"UDP server listening on {host}:{port}")

    while True:
        data, addr = await loop.sock_recvfrom(sock, 1024)
        print(f"UDP received from {addr}: {data}")
        await loop.sock_sendto(sock, data, addr)  # Echo


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
