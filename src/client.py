# ---------------------------------------------------------------------------------------

# Imports
import hashlib
import logging
import os
import pickle
import socket
import threading
import time

# Custom modules
import protocol
import utils
from datasync import DataUpdated
from utils import run_async_in_thread

logging.basicConfig(
    level=logging.DEBUG,
    filename="debug.log",
    format="%(asctime)s %(message)s ",
    datefmt="%H:%M:%S %d/%m/%Y",
)


def log(msg: str):
    logging.debug("[CLT] " + msg)


# Client configuration

ALIVE_INTERVAL = 1  # seconds between IM_ALIVE requests
ALIVE_TIMEOUT = 5

SHARED_FILES_BASE_PATH = "shared_files"


async def login(server_ip: str, user_id: str, ui) -> Client:
    """
    Registers client on server.

    :param server_ip: The IP address of the server to connect to.
    :param user_id: Username of user.
    :return: Returns a Client if successful, otherwise raises an exception.
    :rtype: Client
    """

    try:
        server_id = await _register(server_ip, user_id)
    except Exception as e:
        e.add_note("Login failed. Check your connection or server IP.")
        raise e

    return Client(ui, server_ip, server_id, user_id)


class Client:
    def __init__(self, ui, server_ip: str, server_id: str, user_id: str):
        """
        Create a Client - a collection of state and behaviour associated
        with a registered, active user.

        :param ui: Reference to user interface for callbacks.
        :param server_ip: IP address of server.
        :param user_id: The ID of the user of this client.
        """

        self.ui = ui
        self.server_ip = server_ip
        self.server_id = server_id
        self.user_id = user_id
        self.current_group: int | None = None
        self.groups: dict[int, Group] = {}
        self.last_event_id: int = 0
        self.events: dict[int, protocol.Event] = {}

        self.local_ip = self._get_local_ip()
        log(f"[*] Local IP address is {self.local_ip}")

        # Start listening for P2P requests
        self.p2p_thread = threading.Thread(target=self._listen_p2p, daemon=True)
        self.p2p_thread.start()
        log("[+] P2P thread started.")

        # Start periodic poll for updates
        self.alive_thread = threading.Thread(target=self._im_alive_loop, daemon=True)
        self.alive_thread.start()
        log("[+] IM ALIVE thread started.")

    async def update(self):
        """
        Update the client state by requesting and processing all events since last update.
        Notify the UI to update once completed.
        """

        try:
            events = await self.get_events(self.last_event_id)
        except Exception as e:
            e.add_note("Update failed: GET_EVENTS request failed.")
            raise e

        for event in events:
            if event.eventID not in self.events:
                self.events[event.eventID] = event

                if isinstance(event, protocol.MessageEvent):
                    log(f"[MSG] {event.senderUserID}: {event.message}")
                elif isinstance(event, protocol.FileAvailableEvent):
                    log(f"[FILE] {event.senderUserID} shared {event.fileName}")
                elif isinstance(event, protocol.AddMemberEvent):
                    log(f"[MEMBER] {event.userID} was added by {event.senderUserID}")

                if event.groupID not in self.groups:
                    self.groups[event.groupID] = Group(event.groupID, "", set())

                if isinstance(event, protocol.AddMemberEvent):
                    if event.userID == self.user_id:
                        self.groups[event.groupID].name = event.groupName

                        if event.senderUserID != self.user_id:
                            # Fetch all group events before we got invited so we can access message history.
                            backlog = await self.get_events(
                                0, event.eventID, event.groupID
                            )

                            for event in backlog:
                                if event.eventID not in self.events:
                                    self.events[event.eventID] = event
                                    if isinstance(event, protocol.AddMemberEvent):
                                        self.groups[event.groupID].members.add(
                                            event.userID
                                        )
                    else:
                        self.groups[event.groupID].members.add(event.userID)

        log(f"events: {self.events}")

        if len(events) > 0:
            self.last_event_id = events[-1].eventID

        log("[!] Triggering UI redraw.")
        self.ui.post_message(DataUpdated())

    async def send_message(self, group_id: int, message: str):
        """
        Sends message to specified group.

        :param group_id: Group to send message to.
        :param message: Message to send.
        """
        message_body = message.encode("utf-8")

        request = protocol.PutMessage(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="PUT_MESSAGE",
            groupID=group_id,
            length=len(message_body),
        )

        try:
            log("[*] Message send. Awaiting response.")
            response_header, _ = await _tcp_request(
                self.server_ip, request, message_body
            )
            log("[*] Message response received.")
        except Exception as e:
            e.add_note("Failed to send message: PUT_MESSAGE request failed.")
            raise e

        log(f"[+] Sent message to group_id {group_id}.")
        await self.update()

    async def add_group_member(self, group_id: int, user_id: str):
        """
        Adds user to the specified group.

        :param group_id: Group to add the user as a member of.
        :param user_id: User ID of the new member.
        """

        request = protocol.PutMember(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="PUT_MEMBER",
            groupID=group_id,
            addUserID=user_id,
        )

        try:
            log("[*] Sending PUT_MEMBER request. Awaiting response.")
            response_header, _ = await _tcp_request(self.server_ip, request)
            log("[*] PUT_MEMBER response received.")
        except Exception as e:
            e.add_note("Failed to add group member: PUT_MEMBER request failed.")
            raise e

        log(f"[+] Added member to group_id {group_id}.")
        await self.update()

    async def create_group(self, group_name: str, user_ids: list[str]):
        """
        Creates group with specified members.

        :param group_name: Name of group.
        :param user_ids: List of username to add to group.
        """
        request = protocol.CreateGroup(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="CREATE_GROUP",
            name=group_name,
            members=user_ids,
        )

        try:
            await _tcp_request(self.server_ip, request)
        except Exception as e:
            e.add_note("Failed to create group: CREATE_GROUP request failed.")
            raise e

        log(f"[+] Created group {group_name} successfully.")
        await self.update()

    # Obtains file from peer and writes to disk, returns True if succesful and False if not
    async def get_file(self, peer_user_id: str, sha256_file_id: str, save_path: str):
        """
        :param peer_user_id: Username of peer hosting the file.
        :param sha256_file_id: Hash of file.
        :param save_path: Path file is saved at.
        :return: True if succesful and False if not
        """

        group_id = self.current_group

        if group_id is None:
            raise Exception("Failed to get file: current group is not set.")

        try:
            peer_ip = await self._get_peer(peer_user_id)
            log(f"GET_PEER successful - peer IP: {peer_ip}")
        except Exception as e:
            e.add_note("Failed to get file: GET_PEER request failed.")
            raise e

        try:
            await self._file_request(peer_ip, sha256_file_id, group_id, save_path)
            log("FILE_REQUEST successful")
        except Exception as e:
            e.add_note(
                "Failed to get file: FILE_REQUEST failed. The user might have gone offline."
            )
            raise e

    async def share_file(self, file_path: str):
        """
        Registers a file as available for P2P download by group members.
        Called by the UI when the user shares a file. Also sends _PUT_FILE request to server

        :param group_id: Group to advertise the file to.
        :param file_path: Local path of the file to share.
        :return: True if successful, False if not.
        """

        # Obtain current current group ID immediately (before the user has a chance to switch groups)
        group_id = self.current_group

        if group_id is None:
            raise Exception("Sharing file failed: current group is not set.")

        # Read file and compute SHA256
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            log("[+] Read file successfully.")
        except Exception as e:
            e.add_note(
                f"Sharing file failed: {file_path} is not a file or is not readable."
            )
            raise e

        sha256 = hashlib.sha256(file_bytes).hexdigest().upper()
        log(f"[+] File hash is {sha256}.")

        # Add file to local database which maintains which files have
        # been shared along with sha256 hash and group ID, per user
        # so _handle_p2p_request can serve it.
        self._append_shared_files_registry(
            group_id, sha256, os.path.basename(file_path), file_path
        )

        await self.put_file(group_id, file_path, sha256)

    # ---------------------------------------------------------------------------------------------------------------------
    # Client-Server Request Functions
    # ---------------------------------------------------------------------------------------------------------------------

    async def put_file(self, group_id: int, file_path: str, sha256: str):
        """
        Notifies the server that a file is available for P2P download.

        :param group_id: Group to advertise the file to.
        :param file_path: Local path of the file to share.
        :param sha256: SHA256 hash of the file.
        :return: True if successful, False if not.
        """
        file_name = os.path.basename(file_path)

        request = protocol.PutFile(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="PUT_FILE",
            groupID=group_id,
            sha256=sha256,
            fileName=file_name,
        )

        try:
            response_header, _ = await _tcp_request(self.server_ip, request)
        except Exception as e:
            e.add_note("Failed to make file available: PUT_FILE request failed.")
            raise e

        log(f"[+] {file_name} advertised to group {group_id}.")
        await self.update()

    async def get_events(
        self,
        after_event_id: int,
        before_event_id: int | None = None,
        group_id: int | None = None,
    ) -> list[protocol.Event]:
        """
        Fetch a list of events. The events listed by the response are only those which the requesting user is a member of.

        :param last_event_id: Only request events after this event ID.
        :param group_id: Only request events for this group.
        :returns: The list of events within the specified parameters.
        """

        request = protocol.GetEvents(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="GET_EVENTS",
            groupID=group_id,
            beforeEventID=before_event_id,
            afterEventID=after_event_id,
        )

        try:
            log("[*] Awaiting TCP response.")
            _, response_body_bytes = await _tcp_request(self.server_ip, request)
            log("[*] TCP response received.")
        except Exception as e:
            e.add_note("Getting events failed: GET_EVENTS request failed.")
            raise e

        if not response_body_bytes:
            raise Exception("Getting events failed: no response body length.")

        try:
            events_json = response_body_bytes.decode("utf-8")
            events = protocol.parse_events_response_body(events_json)
            return events
        except Exception as e:
            e.add_note(
                "Getting events failed: decoding and parsing events list failed."
            )
            raise e

    async def _get_peer(self, peer_user_id: str) -> str:
        """
        Request the most recently advertised localIP for a member of the group which the requesting user is also on.
        This facilitates the ability of a client to initiate a P2P exchange with another client.
        """

        if not self.current_group:
            raise Exception("Failed to get peer IP: current group not set.")

        request = protocol.GetPeer(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="GET_PEER",
            peerUserID=peer_user_id,
            groupID=self.current_group,
        )

        try:
            response_header, peer_ip_bytes = await _tcp_request(self.server_ip, request)
        except Exception as e:
            e.add_note("Failed to get peer IP: GET_PEER request failed.")
            raise e

        if not peer_ip_bytes:
            raise Exception(
                f"Failed to get peer IP: GET_PEER for user ID {peer_user_id} succeeded, but response did not include the IP."
            )

        peer_ip = peer_ip_bytes.decode("utf-8")
        return peer_ip

    # ---------------------------------------------------------------------------------------------------------------------
    # P2P request and response methods
    # ---------------------------------------------------------------------------------------------------------------------

    # Requests file from peer and saves it if file transferred succesfully
    async def _file_request(
        self, peer_ip: str, sha256_file_id: str, group_id: int, save_path: str
    ):
        """Requests file from peer and saves it if file transferred succesfully"""

        request = protocol.FileRequest(
            version=protocol.MAP_VER,
            userID=self.user_id,
            serverID=self.server_id,
            type="FILE_REQUEST",
            groupID=group_id,
            sha256=sha256_file_id,
        )

        try:
            response_header, response_body_bytes = await _tcp_request(
                peer_ip, request, b"", protocol.CLIENT_P2P_PORT
            )
        except Exception as e:
            e.add_note("Failed to request file: FILE_REQUEST request failed.")
            raise e

        if (
            not isinstance(response_header, protocol.BodyResponse)
            or response_body_bytes is None
        ):
            raise Exception(
                "Failed to request file: FILE_REQUEST succeeded but didn't return a body."
            )

        # Verifying file integrity
        computed_hash = hashlib.sha256(response_body_bytes).hexdigest().upper()
        if computed_hash != sha256_file_id or response_header.length != len(
            response_body_bytes
        ):
            raise Exception(
                "Failed to request file: file from user failed to validate."
            )

        try:
            # Write raw bytes directly to disk
            with open(save_path, "wb") as f:
                f.write(response_body_bytes)
        except Exception as e:
            e.add_note("Failed to request file: writing file to disk failed.")
            raise e

    async def _handle_p2p_request(self, sock: socket.socket, peer_ip):
        """Responds to P2P request, sending appropriate response header along with requested file (if
        valid file was requested)

        """
        try:
            stream = protocol.MapStreamBuffer(sock)

            while True:
                response_body = None

                try:
                    header_bytes = await stream.read_header()

                    header = protocol.parse_request_header(header_bytes, self.server_id)

                    if not isinstance(header, protocol.FileRequest):
                        raise protocol.Status(protocol.STATUS_BAD_REQUEST)

                    # Look for shared file which matches sha256 hash of request
                    file_path = next(
                        (
                            f
                            for _, f_sha256, _, f in self._load_shared_files_registry()
                            if f_sha256 == header.sha256
                        ),
                        None,
                    )

                    log(f"File Path: {file_path}")

                    # If we can't find the SHA256 or the file no longer exists, indicate
                    # that the file is unavailable.
                    if file_path is None or not os.path.exists(file_path):
                        raise protocol.Status(protocol.STATUS_FILE_UNAVAILABLE)

                    # If file matching sha256 hash from request does exist and is shared, parse it
                    # and formulate appropriate header.
                    try:
                        with open(file_path, "rb") as f:
                            response_body = f.read()
                            response_header = protocol.BodyResponse(
                                version=protocol.MAP_VER,
                                serverID=self.server_id,
                                status=protocol.STATUS_OK,
                                length=len(response_body),
                            )
                    except Exception as _:
                        raise protocol.Status(protocol.STATUS_FILE_UNAVAILABLE)

                except protocol.Status as s:
                    response_header = protocol.GenericResponse(
                        version=protocol.MAP_VER,
                        serverID=self.server_id,
                        status=s.status,
                    )

                response_header_json = response_header.model_dump_json()
                response_header_bytes = response_header_json.encode("utf-8")

                # Send response header
                sock.sendall(response_header_bytes)
                sock.sendall(b"\x03")

                # Send file (response body)
                if response_body:
                    print(f"< P2P TCP sending to {peer_ip}: {response_body}")
                    sock.sendall(response_body)

        except ConnectionError as _:
            pass
        finally:
            sock.close()
            print(f"TCP closed: {peer_ip}")

    # ---------------------------------------------------------------------------------------------------------------------
    # P2P Listening & Handling and IM_ALIVE heartbeat thread loops
    # ---------------------------------------------------------------------------------------------------------------------

    def _listen_p2p(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", protocol.CLIENT_P2P_PORT))
        server_sock.listen(10)

        while True:
            peer_sock, (peer_ip, peer_port) = server_sock.accept()
            utils.run_async_in_thread(self._handle_p2p_request(peer_sock, peer_ip))

    def _im_alive_loop(self):
        """
        Periodically polls the server for updates.
        """
        while True:
            try:
                request = protocol.ImAlive(
                    version=protocol.MAP_VER,
                    userID=self.user_id,
                    serverID=self.server_id,
                    type="IM_ALIVE",
                    localIP=self.local_ip,
                    afterEventID=self.last_event_id,
                )

                response = _udp_request(self.server_ip, request)
                log("[@] I AM ALIVE")

                if (
                    isinstance(response, protocol.ImAliveResponse)
                    and response.isOutdated
                ):
                    log("[@] Events are outdated")
                    run_async_in_thread(self.update())

                time.sleep(ALIVE_INTERVAL)

            except Exception as e:
                log(str(e))

    # ---------------------------------------------------------------------------------------------------------------------
    # Internal Helpers
    # ---------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _get_local_ip() -> str:
        """
        Obtain local IP so that user doesn't have to enter it manually.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't actually send anything
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    def _shared_files_registry_path(self) -> str:
        keepcharacters = (" ", "_")
        pathsafe_user_id = "".join(
            c for c in self.user_id if c.isalnum() or c in keepcharacters
        ).rstrip()

        return SHARED_FILES_BASE_PATH + "." + pathsafe_user_id + ".pkl"

    def _load_shared_files_registry(self) -> list[tuple[int, str, str, str]]:
        """Load shared files registry from disk, returning empty list if not found."""

        path = self._shared_files_registry_path()

        try:
            if not os.path.isfile(path):
                return []

            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            e.add_note(f"Loading shared files registry failed: opening {path} failed.")
            raise e

    def _append_shared_files_registry(
        self, group_id: int, sha256: str, file_name: str, file_path: str
    ):
        """Persist shared files registry to disk."""

        try:
            shared = self._load_shared_files_registry()
        except Exception as e:
            e.add_note(
                "Appending to shared files registry failed: could not load registry."
            )
            raise e

        shared.append((group_id, sha256, file_name, file_path))

        try:
            with open(self._shared_files_registry_path(), "wb") as f:
                pickle.dump(shared, f)
        except Exception as e:
            e.add_note(
                "Appending to shared files registry failed: could not write to registry file."
            )
            raise e


# ---------------------------------------------------------------------------------------------------------------------
# Server communication
# ---------------------------------------------------------------------------------------------------------------------


async def _tcp_request(
    ip_address: str,
    header: protocol.BaseRequest,
    body: bytes = b"",
    port: int = protocol.SERVER_TCP_PORT,
) -> tuple[protocol.Response, bytes | None]:
    """
    Creates and sends TCP request, and returns Response object with response header and body.

    :param ip_address: IP address of server; defaults to localhost.
    """

    expected_server_id = header.serverID

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        sock.connect((ip_address, port))
    except Exception as e:
        e.add_note("TCP request failed: connect failed.")
        raise e

    # Serialize header data to JSON and encode as UTF-8
    header_bytes = header.model_dump_json().encode("utf-8")
    # Build payload
    payload = header_bytes + protocol.HEADER_BODY_DELIMITER + body

    log(f"[=] TCP request payload {payload}")
    sock.sendall(payload)

    stream = protocol.MapStreamBuffer(sock)
    response_header_bytes = await stream.read_header()
    log(f"[=] TCP response header bytes {response_header_bytes}")
    response_header_json = response_header_bytes.decode("utf-8")
    response_header = protocol.parse_response_header(response_header_json)

    if response_header.status != protocol.STATUS_OK:
        raise Exception(f"TCP request failed: status was {response_header.status}")

    try:
        protocol.check_versions_match(protocol.MAP_VER, response_header.version)
    except Exception as e:
        e.add_note(f"TCP request failed: server version was {response_header.version}")
        raise e

    if expected_server_id:
        if response_header.serverID != expected_server_id:
            raise Exception("TCP request failed: wrong server ID in response.")

    # Generic response header doesn't have length field, and no body
    if isinstance(response_header, protocol.BodyResponse):
        response_body_bytes = await stream.read_body(response_header.length)
    else:
        response_body_bytes = None

    sock.close()

    return response_header, response_body_bytes


async def _register(server_ip: str, user_id: str) -> str:
    """
    Register the user to the server if they are not yet registered.
    This implicitly confirms whether the server is reachable and speaks a compatible MAP version.

    :param server_ip: The IP of the server to connect and register with.
    :returns: The server ID, if the request was successful.
    """

    request = protocol.Register(
        version=protocol.MAP_VER,
        type="REGISTER",
        userID=user_id,
        serverID="",
    )

    try:
        response, _ = await _tcp_request(server_ip, request)
    except Exception as e:
        e.add_note("Registration failed: REGISTER request did not succeed.")
        raise e

    return response.serverID


def _udp_request(
    ip_address,
    header: protocol.BaseRequest,
    port=protocol.SERVER_UDP_PORT,
) -> protocol.Response:
    """
    Sends UDP request, returns Response object.

    :param ip_address: IP address of server; defaults to localhost.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Very important, otherwise hangs forever on sock.recvfrom(65535)
    sock.settimeout(ALIVE_TIMEOUT)

    # Build payload
    # No request body or response body is accomodated for here as it is not needed.
    header_bytes = header.model_dump_json().encode("utf-8")

    sock.sendto(header_bytes, (ip_address, port))

    # Receive response and parse
    try:
        response_header_bytes, _ = sock.recvfrom(65535)
        response_header_json = response_header_bytes.rstrip(
            protocol.HEADER_BODY_DELIMITER
        ).decode("utf-8")
        sock.close()
        return protocol.parse_response_header(response_header_json)
    except socket.timeout:
        raise Exception("UDP request failed: request timed out.")
    finally:
        sock.close()


class Group:
    def __init__(self, id: int, name: str, members: set[str]):
        self.id = id
        self.name = name
        self.members: set[str] = members


if __name__ == "__main__":
    print("[-] Use the test file to run the client directly.")
