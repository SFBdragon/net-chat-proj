# ---------------------------------------------------------------------------------------

# Imports
import hashlib
import logging
import os
import socket
import threading
import time
from typing import Optional

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


# Client configuration

MAP_VERSION = "1.0"
TCP_PORT = 3030
UDP_PORT = 3031
P2P_PORT = 3032

ALIVE_INTERVAL = 2  # seconds between IM_ALIVE requests
ALIVE_TIMEOUT = 5
HEADER_BODY_DELIMITER = b"\x03"

MOD_CODE = "[CLT] "

default_server_ip = "127.0.0.1"

threads = []
tasks = []


class Client:
    def __init__(self, ui, server_ip):
        """
        Sets client configuration.

        :param ui: Reference to user interface for callbacks.
        :param server_ip: IP address of server.
        """
        self.server_ip = server_ip
        self.local_ip = self._get_local_ip()
        print(f"[*] Local IP address is {self.local_ip}")
        logging.debug(MOD_CODE + f"[*] Local IP address is {self.local_ip}")

        # Maintains state of client backend for the UI to reference when refreshing
        # Only set after succesful REGISTER
        self.AppState = None
        self.ui = ui

    # REGISTER request to server, called by GUI when login button pressed
    async def login(self, user_id: str, server_id="") -> bool:
        """
        Registers client on server.

        :param user_id: Username of user.
        :param server_id: Unique server identifier.
        :return: Login status; whether login was successful or not.
        :rtype: bool
        """
        login_status = await self._REGISTER(user_id, server_id)
        if login_status == True:
            # Start listening for P2P requests
            p2p_thread = threading.Thread(target=self._listen_P2P, daemon=True)
            threads.append(p2p_thread)
            p2p_thread.start()
            logging.debug(MOD_CODE + "[+] P2P thread started.")

            # Start periodic poll for updates
            logging.debug(MOD_CODE + "[+] IM ALIVE thread started.")
            alive_thread = threading.Thread(target=self._im_alive_loop, daemon=True)
            threads.append(alive_thread)
            alive_thread.start()

        return login_status

    async def send_message(self, group_id: int, message: str):
        """
        Sends message to specified group.

        :param group_id: Group to send message to.
        :param message: Message to send.
        """
        message_body = message.encode("utf-8")

        request = protocol.PutMessage(
            version=protocol.MAP_VER,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="PUT_MESSAGE",
            groupID=group_id,
            length=len(message_body),
        )

        logging.debug(MOD_CODE + "[*] Message send. Awaiting response.")
        response_header, _ = await self._tcp_request(
            request, self.server_ip, message_body
        )
        logging.debug(MOD_CODE + "[*] Message response received.")

        if response_header.status == protocol.STATUS_OK:
            print(f"[+] Send message to group_id {group_id} successfully.")
            logging.debug(
                MOD_CODE + f"[+] Send message to group_id {group_id} successfully."
            )
            await self.GET_EVENTS()

    async def add_user_to_group(self, group_id: int, user_id: str):
        """
        Adds user to the specified group.

        :param group_id: Group to add the user as a member of.
        :param user_id: User ID of the new member.
        """

        request = protocol.PutMember(
            version=protocol.MAP_VER,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="PUT_MEMBER",
            groupID=group_id,
            addUserID=user_id,
        )

        logging.debug(MOD_CODE + "[*] Sending PUT_MEMBER request. Awaiting response.")
        response_header, _ = await self._tcp_request(request, self.server_ip)
        logging.debug(MOD_CODE + "[*] PUT_MEMBER response received.")

        if response_header.status == protocol.STATUS_OK:
            logging.debug(
                MOD_CODE + f"[+] Added member to group_id {group_id} successfully."
            )
            await self.GET_EVENTS()

    async def create_group(self, group_name: str, user_ids: list[str]):
        """
        Creates group with specified members.

        :param group_name: Name of group.
        :param user_ids: List of username to add to group.
        """
        request = protocol.CreateGroup(
            version=protocol.MAP_VER,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="CREATE_GROUP",
            name=group_name,
            members=user_ids,
        )

        response_header, _ = await self._tcp_request(request, self.server_ip)

        if response_header.status == protocol.STATUS_OK:
            print(f"[+] Created group {group_name} successfully.")
            logging.debug(MOD_CODE + f"[+] Created group {group_name} successfully.")
            await self.GET_EVENTS()

    # TODO
    # def add_to_group(user_ids: list[str]) -> bool:

    # Obtains file from peer and writes to disk, returns True if succesful and False if not
    async def get_file(
        self, peer_user_id: str, sha256_file_id: str, save_path: str
    ) -> bool:
        """
        :param peer_user_id: Username of peer hosting the file.
        :param sha256_file_id: Hash of file.
        :param save_path: Path file is saved at.
        :return: True if succesful and False if not
        """

        group_id = self.AppState["current_group"]
        peer_ip = await self._GET_PEER(peer_user_id)

        file_req_status = await self.FILE_REQUEST(
            peer_ip, sha256_file_id, group_id, save_path
        )
        return file_req_status

    async def share_file(self, file_path: str) -> bool:
        """
        Registers a file as available for P2P download by group members.
        Called by the UI when the user shares a file. Also sends _PUT_FILE request to server

        :param group_id: Group to advertise the file to.
        :param file_path: Local path of the file to share.
        :return: True if successful, False if not.
        """
        group_id = self.AppState[
            "current_group"
        ]  # Obtain current group id ASAP when function called by UI
        # Read file and compute SHA256
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        logging.debug("[+] Read file successfully.")

        sha256 = hashlib.sha256(file_bytes).hexdigest().upper()
        logging.debug("[+] File hash is {sha256}.")

        # Add file to local dict which maintains which files have been shared along with sha256 hash,
        #  so _handle_p2p_request can serve it
        self.AppState["shared_files"][sha256] = file_path

        logging.debug("[+] Calling PUT_FILE.")
        return await self._PUT_FILE(group_id, file_path, sha256)

    # ---------------------------------------------------------------------------------------------------------------------
    # Client-Server Request Functions
    # ---------------------------------------------------------------------------------------------------------------------

    async def _PUT_FILE(self, group_id: int, file_path: str, sha256: str) -> bool:
        """
        Notifies the server that a file is available for P2P download.

        :param group_id: Group to advertise the file to.
        :param file_path: Local path of the file to share.
        :param sha256: SHA256 hash of the file.
        :return: True if successful, False if not.
        """
        file_name = os.path.basename(file_path)

        request = protocol.PutFile(
            version=MAP_VERSION,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="PUT_FILE",
            groupID=group_id,
            sha256=sha256,
            fileName=file_name,
        )

        response_header, _ = await self._tcp_request(request, self.server_ip)

        if response_header.status == protocol.STATUS_OK:
            print(f"[+] File {file_name} advertised to group {group_id} successfully.")
            logging.debug(
                MOD_CODE + f"[+] File {file_name} advertised to group {group_id}."
            )
            await self.GET_EVENTS()
            return True

        logging.debug(
            MOD_CODE
            + f"[-] Failed to advertise file {file_name}: {response_header.status}"
        )
        return False

    async def _REGISTER(self, user_id: str, server_id="") -> bool:
        """
        Verify server reachability, protocol compatibility, and register the user ID with the server.
        """
        # Header for REGISTER request
        request = protocol.Register(
            version=MAP_VERSION, type="REGISTER", userID=user_id, serverID=server_id
        )

        response_header, _ = await self._tcp_request(request, self.server_ip)

        if response_header.status == protocol.STATUS_OK:
            # Only do this if registration was succesful, i.e. STATUS_OK
            self.AppState = {
                "user_id": user_id,
                "server_id": response_header.serverID,
                "groups": {
                    # "group_name": {
                    #     "group_id": int,
                    #     "members": []   # list of user_id strings
                    # }
                },
                "events": [],  # ordered list of event dicts from GET_EVENTS
                "current_group": None,  # group_name of whichever group the user has open
                "last_event_id": 0,
                "error": "",
                "shared_files": {},  # sha256 -> local file path for shared files
            }
            logging.debug(MOD_CODE + "[+] Successfully registered on the server.")
            return True

        logging.debug(MOD_CODE + "[-] Failed to register on the server.")
        return False

    # Returns all events after the latest eventID as a list of protocol.Event objects
    async def GET_EVENTS(self) -> list[protocol.Event]:
        """
        Fetch a list of events. The events listed by the response are only those which the requesting user is a member of.
        """
        request = protocol.GetEvents(
            version=MAP_VERSION,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="GET_EVENTS",
            groupID=None,
            beforeEventID=None,
            afterEventID=self.AppState["last_event_id"],
        )

        logging.debug(MOD_CODE + "[*] Awaiting TCP response.")
        _, response_body_bytes = await self._tcp_request(request, self.server_ip)
        logging.debug(MOD_CODE + "[*] TCP response received.")

        # Guarding for if no new events
        if response_body_bytes:
            response_body_json = response_body_bytes.decode("utf-8")
            response_body_list = protocol.parse_events_response_body(response_body_json)

            initialLoad = False
            if self.AppState["last_event_id"] == 0:
                initialLoad = True
                self.AppState["events"] = response_body_list

            # Set last event ID to the last event in the returned list
            self.AppState["last_event_id"] = response_body_list[-1].eventID

            for event in response_body_list:
                if not initialLoad:
                    self.AppState["events"].append(event)

                if isinstance(event, protocol.MessageEvent):
                    print(f"[MSG] {event.senderUserID}: {event.message}")
                elif isinstance(event, protocol.FileAvailableEvent):
                    print(f"[FILE] {event.senderUserID} shared {event.fileName}")
                elif isinstance(event, protocol.AddMemberEvent):
                    print(f"[MEMBER] {event.userID} was added by {event.senderUserID}")

                    group_id = str(event.groupID)

                    if group_id not in self.AppState["groups"]:
                        self.AppState["groups"][group_id] = {
                            "group_id": event.groupID,
                            "group_name": event.groupName,
                            "members": [],
                        }

                    self.AppState["groups"][group_id]["members"].append(event.userID)

                    print(self.AppState["groups"])

            # tell TUI to redraw
            logging.debug(MOD_CODE + "[!] Attempting to broadcast data update.")
            self.ui.post_message(DataUpdated())
        else:
            response_body_list = None

        return response_body_list

    async def _GET_PEER(self, peer_user_id: str) -> str:
        """
        Request the most recently advertised localIP for a member of the group which the requesting user is also on.
        This facilitates the ability of a client to initiate a P2P exchange with another client.
        """
        request = protocol.GetPeer(
            version=MAP_VERSION,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="GET_PEER",
            peerUserID=peer_user_id,
            groupID=self.AppState["current_group"],
        )

        response_header, response_body_bytes = await self._tcp_request(
            request, self.server_ip
        )

        response_body_str = response_body_bytes.decode("utf-8")  # Peer IP Address

        if response_header.status == protocol.STATUS_OK:
            return response_body_str

        return "0.0.0.0"

        # TODO: Add error handling here?

    # ---------------------------------------------------------------------------------------------------------------------
    # P2P request and response methods
    # ---------------------------------------------------------------------------------------------------------------------

    # Requests file from peer and saves it if file transferred succesfully
    async def FILE_REQUEST(
        self, peer_ip: str, sha256_file_id: str, group_id: int, save_path: str
    ) -> bool:
        """Requests file from peer and saves it if file transferred succesfully"""

        request = protocol.FileRequest(
            version=MAP_VERSION,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="FILE_REQUEST",
            groupID=group_id,
            sha256=sha256_file_id,
        )

        response_header, response_body_bytes = await self._tcp_request(
            request, peer_ip, b"", P2P_PORT
        )

        if response_header.status != protocol.STATUS_OK:
            return False

        # Verifying file integrity
        computed_hash = hashlib.sha256(response_body_bytes).hexdigest().upper()
        if computed_hash != sha256_file_id or response_header.length != len(
            response_body_bytes
        ):
            return False

        # Write raw bytes directly to disk
        with open(save_path, "wb") as f:
            f.write(response_body_bytes)

        return True

    async def _handle_p2p_request(self, sock: socket.socket, peer_ip):
        """Responds to P2P request, sending appropriate response header along with requested file (if
        valid file was requested)

        """
        try:
            stream = protocol.MapStreamBuffer(sock)

            while True:
                header_bytes = await stream.read_header()
                print(f"> TCP received from {peer_ip}: {header_bytes}")

                response_body = None

                try:
                    header = protocol.parse_request_header(
                        header_bytes, self.AppState["server_id"]
                    )

                    sha256 = header.sha256

                    # Look for shared file which matches sha256 hash of request
                    file_path = self.AppState["shared_files"].get(
                        sha256
                    )  # None if not found

                    # If file matching sha256 hash from request does exist and is shared, parse it
                    #  and formulate appropriate header
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            response_body = f.read()

                            response_header = protocol.BodyResponse(
                                version=protocol.MAP_VER,
                                serverID=self.AppState["server_id"],
                                status=protocol.STATUS_OK,
                                length=len(response_body),
                            )
                    else:
                        response_body = None
                        response_header = protocol.GenericResponse(
                            version=protocol.MAP_VER,
                            serverID=self.AppState["server_id"],
                            status=protocol.STATUS_FILE_UNAVAILABLE,
                        )

                except protocol.Status as s:
                    response_header = protocol.GenericResponse(
                        version=protocol.MAP_VER,
                        serverID=self.AppState["server_id"],
                        status=s.status,
                    )

                response_json = response_header.model_dump_json()
                response_bytes = response_json.encode("utf-8")

                # Send response header
                print(f"< P2P TCP sending to {peer_ip}: {response_json}\x03")
                sock.sendall(response_bytes)
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
    # Server communication
    # ---------------------------------------------------------------------------------------------------------------------

    async def _tcp_request(
        self,
        header: protocol.BaseRequest,
        ip_address=default_server_ip,
        body: bytes = b"",
        port=TCP_PORT,
    ) -> tuple[protocol.Response, Optional[bytes]]:
        """
        Creates and sends TCP request, and returns Response object with response header and body.

        :param ip_address: IP address of server; defaults to localhost.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((ip_address, port))

        # Build payload (serialise using JSON)
        header_bytes = header.model_dump_json().encode("utf-8")
        if body:
            payload = header_bytes + HEADER_BODY_DELIMITER + body
        else:
            payload = header_bytes + HEADER_BODY_DELIMITER

        sock.sendall(payload)
        print(f"[+] Payload sent ({len(payload)}) characters.")

        stream = protocol.MapStreamBuffer(sock)
        response_header_bytes = await stream.read_header()
        logging.debug(MOD_CODE + f"[=] TCP request payload {payload}")
        logging.debug(
            MOD_CODE + f"[=] TCP response header bytes {response_header_bytes}"
        )
        response_header_json = response_header_bytes.decode("utf-8")
        response_header = protocol.parse_response_header(response_header_json)

        if isinstance(
            response_header, protocol.BodyResponse
        ):  # Generic response header doesn't have length field
            response_body_bytes = await stream.read_body(response_header.length)
        else:
            response_body_bytes = None

        sock.close()
        return response_header, response_body_bytes

    def _udp_request(
        self, header: protocol.BaseRequest, ip_address=default_server_ip
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

        sock.sendto(header_bytes, (ip_address, UDP_PORT))

        # Receive response and parse
        try:
            response_header_bytes, _ = sock.recvfrom(65535)
            print("Completed UDP")
            response_header_json = response_header_bytes.rstrip(
                protocol.HEADER_BODY_DELIMITER
            ).decode("utf-8")
            sock.close()
            return protocol.parse_response_header(response_header_json)
        except socket.timeout:
            print("[!] UDP request timed out")
            logging.debug(MOD_CODE + "[!] UDP request timed out.")
            sock.close()
            return None

    # ---------------------------------------------------------------------------------------------------------------------
    # TODO: Thread loops
    # ---------------------------------------------------------------------------------------------------------------------

    def _listen_P2P(self):

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", P2P_PORT))
        server_sock.listen(10)

        print(f"Listening for P2P requests")

        while True:
            peer_sock, (peer_ip, peer_port) = server_sock.accept()
            utils.run_async_in_thread(self._handle_p2p_request(peer_sock, peer_ip))

    def _im_alive_loop(self):
        """
        Periodically polls the server for updates.
        """
        try:
            while True:
                request = protocol.ImAlive(
                    version=MAP_VERSION,
                    userID=self.AppState["user_id"],
                    serverID=self.AppState["server_id"],
                    type="IM_ALIVE",
                    localIP=self.local_ip,
                    afterEventID=self.AppState["last_event_id"],
                )
                print("TRYING UDP")
                response = self._udp_request(request, self.server_ip)
                logging.debug(MOD_CODE + "[@] I AM ALIVE")

                if (
                    isinstance(response, protocol.ImAliveResponse)
                    and response.isOutdated
                ):
                    logging.debug(MOD_CODE + "[@] Events are outdated")
                    run_async_in_thread(self.GET_EVENTS())

                time.sleep(ALIVE_INTERVAL)

        except Exception as e:
            logging.debug(MOD_CODE + str(e))

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

    # -------------------------------------------------------------------------------------------------------------------------


if __name__ == "__main__":
    print("[-] Use the test file to run the client directly.")
