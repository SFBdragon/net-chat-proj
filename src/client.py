import json
import socket
import threading
<<<<<<< Updated upstream
=======
import time
import os
from typing import Optional

# Custom modules
>>>>>>> Stashed changes
import protocol
import hashlib
from typing import Optional
import asyncio
import time

MAP_VERSION = "1.0"
TCP_PORT = 3030
UDP_PORT = 3031
P2P_PORT = 3032
SERVER_IP = "127.0.0.1"

ALIVE_INTERVAL = 2  # seconds between IM_ALIVE requests
ALIVE_TIMEOUT = 5
HEADER_BODY_DELIMITER = b"\x03"


threads = []

class Client:

    def __init__(self): #TODO UI Callback function will be a parameter here

        self.local_ip = self._get_local_ip()
        print(f"[*] Local IP address is {self.local_ip}")

        #Maintains state of client backend for the UI to reference when refreshing
        #only given values after succesful REGISTER
        self.AppState = None

        #Callback function
        #self.on_state_update = ui_refresh

#---------------------------------------------------------------------------------------------------------------------
#Public API for GUI
#---------------------------------------------------------------------------------------------------------------------

    #REGISTER request to server, called by GUI when login button pressed
    async def login(self, user_id: str, server_id = "") -> bool:

<<<<<<< Updated upstream
        login_status = await self._REGISTER(user_id, server_id)

=======
        :param user_id: Username of user.
        :param server_id: Unique server identifier.
        :return: Login status; whether login was successful or not.
        :rtype: bool
        """
        login_status, serverID = await self._REGISTER(user_id, server_id)
>>>>>>> Stashed changes
        if login_status == True:

            #Create appState
            # Only do this if registration was succesful, i.e. STATUS_OK
            self.AppState = {
                "user_id": user_id,
                "server_id": serverID,
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
                "shared_files": {}  # sha256 -> local file path for shared files

            }

            # Start listening for P2P requests
            p2p_thread = threading.Thread(target=self._listen_P2P, daemon=True)
            threads.append(p2p_thread)
            p2p_thread.start()

            # Start thread for IM_ALIVE
            im_alive_thread = threading.Thread(target=self._im_alive_loop, daemon=True)
            threads.append(im_alive_thread)
            im_alive_thread.start()
        
        return login_status
    
    
    async def send_message(self, group_id: int, message: str) -> bool:

        message_body = message.encode("utf-8")

        request = protocol.PutMessage(
            version=protocol.MAP_VER,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="PUT_MESSAGE",
            groupID=group_id,
            length=len(message_body),
        )

<<<<<<< Updated upstream
        response_header, _ = await self._tcp_request(request, message_body)
=======
        logging.debug(MOD_CODE + "[*] Message send. Awaiting response.")
        response_header, _ = await self._tcp_request(request, self.server_ip, message_body)
        logging.debug(MOD_CODE + "[*] Message response received.")
>>>>>>> Stashed changes

        if(response_header.status == protocol.STATUS_OK):
            print(f"[+] Send message to group_id {group_id} successfully.")

    async def create_group(self, group_name: str, user_ids: list[str]) -> bool:
        request = protocol.CreateGroup(
            version=protocol.MAP_VER,
            userID=self.AppState["user_id"],
            serverID=self.AppState["server_id"],
            type="CREATE_GROUP",
            name=group_name,
            members=user_ids,
        )
<<<<<<< Updated upstream
        
        response_header, _ = await self._tcp_request(request)
=======

        response_header, _ = await self._tcp_request(request, self.server_ip)
>>>>>>> Stashed changes

        if(response_header.status == protocol.STATUS_OK):
            print(f"[+] Created group {group_name} successfully.")

    #TODO
    #def add_to_group(user_ids: list[str]) -> bool:

    #Obtains file from peer and writes to disk, returns True if succesful and False if not
    def get_file(self, peer_user_id: str, sha256_file_id: str, save_path: str) -> bool:

<<<<<<< Updated upstream
        group_id = self.AppState["current_group"] 
        peer_ip = self.GET_PEER(peer_user_id)
=======
        :param peer_user_id: Username of peer hosting the file.
        :param sha256_file_id: Hash of file.
        :param save_path: Path file is saved at.
        :return: True if succesful and False if not
        """

        group_id = self.AppState["current_group"]
        peer_ip = self._GET_PEER(peer_user_id)
>>>>>>> Stashed changes

        return self.FILE_REQUEST(peer_ip, sha256_file_id,group_id, save_path)
    
    #TODO
    #def share_file(content: bytes = b"") -> bool:

<<<<<<< Updated upstream

    #TODO: Implement method to update TUI whenever AppState changes due to new messages etc.
    def send_update(self):
        self.on_state_update("data1")

#---------------------------------------------------------------------------------------------------------------------
#Client-server request functions
#---------------------------------------------------------------------------------------------------------------------

    #REGISTER request as defined in specification
    #returns true if succesful, false if not
    async def _REGISTER(self, user_id: str, server_id = "") -> bool:
    #Header for REGISTER request

=======

    async def share_file(self, file_path: str) -> bool:
        """
        Registers a file as available for P2P download by group members.
        Called by the UI when the user shares a file. Also sends _PUT_FILE request to server

        :param group_id: Group to advertise the file to.
        :param file_path: Local path of the file to share.
        :return: True if successful, False if not.
        """
        group_id = self.AppState["current_group"] #Obtain current group id ASAP when function called by UI
        # Read file and compute SHA256
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        sha256 = hashlib.sha256(file_bytes).hexdigest().upper()

        #Add file to local dict which maintains which files have been shared along with sha256 hash,
        #  so _handle_p2p_request can serve it
        self.AppState["shared_files"][sha256] = file_path

        return await self._PUT_FILE(group_id, file_path, sha256)
    

    # ---------------------------------------------------------------------------------------------------------------------
    # Client-Server Request Functions
    # ---------------------------------------------------------------------------------------------------------------------

    
    async def _PUT_FILE(self, group_id:int, file_path: str, sha256: str) -> bool:
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
            logging.debug(MOD_CODE + f"[+] File {file_name} advertised to group {group_id}.")
            await self.GET_EVENTS()
            return True

        logging.debug(MOD_CODE + f"[-] Failed to advertise file {file_name}: {response_header.status}")
        return False

    async def _REGISTER(self, user_id: str, server_id="") -> tuple[bool, serverID:str]:
        """
        Verify server reachability, protocol compatibility, and register the user ID with the server.
        """
        # Header for REGISTER request
>>>>>>> Stashed changes
        request = protocol.Register(
        version= MAP_VERSION,
        type="REGISTER",
        userID=user_id,
        serverID=server_id
        )

        response_header, _ = await self._tcp_request(request, self.server_ip)

<<<<<<< Updated upstream

        if(response_header.status == protocol.STATUS_OK):

            #Only do this if registration was succesful, i.e. STATUS_OK
            self.AppState = {
            "user_id": user_id,
            "server_id": response_header.serverID,
            "groups": {
                # "group_name": {
                #     "group_id": int,
                #     "members": []   # list of user_id strings
                # }
            },
            "events": [],        # ordered list of event dicts from GET_EVENTS
            "current_group": None,  # group_name of whichever group the user has open
            "last_event_id": 0,
            "error": ""
            }
            return True

        return False
=======
        if response_header.status == protocol.STATUS_OK:
            logging.debug(MOD_CODE + "[+] Successfully registered on the server.")
            return True, response_header.serverID

        logging.debug(MOD_CODE + "[-] Failed to register on the server.")
        return False, ""
>>>>>>> Stashed changes


    #Returns all events after the latest eventID as a list of protocol.Event objects
    async def GET_EVENTS(self) -> list[protocol.Event]:
        request = protocol.GetEvents(
        version=MAP_VERSION,
        userID=self.AppState["user_id"],
        serverID=self.AppState["server_id"],
        type="GET_EVENTS",
        groupID=None,
        beforeEventID=None,
        afterEventID=self.AppState["last_event_id"]
    )

<<<<<<< Updated upstream
        _, response_body_bytes = await self._tcp_request(request)
        
=======
        logging.debug(MOD_CODE + "[*] Awaiting TCP response.")
        _, response_body_bytes = await self._tcp_request(request, self.server_ip)
        logging.debug(MOD_CODE + "[*] TCP response received.")

>>>>>>> Stashed changes
        response_body_json = response_body_bytes.decode("utf-8")
        response_body_list = protocol.parse_events_response_body(response_body_json)

        #Set last event ID to the last event in the returned list   
        self.AppState["last_event_id"] = response_body_list[-1].eventID
<<<<<<< Updated upstream
        
        
        return response_body_list

    #Obtains IP Address of peer for P2P file sharing
    async def GET_PEER(self, peer_user_id: str) -> str:

=======

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

        return response_body_list

    async def _GET_PEER(self, peer_user_id: str) -> str:
        """
        Request the most recently advertised localIP for a member of the group which the requesting user is also on.
        This facilitates the ability of a client to initiate a P2P exchange with another client.
        """
>>>>>>> Stashed changes
        request = protocol.GetPeer(
            version = MAP_VERSION,
            userID = self.AppState["user_id"],
            serverID = self.AppState["server_id"],
            type = "GET_PEER",
            peerUserID = peer_user_id,
            groupID = self.AppState["current_group"]
        )

        response_header, response_body_bytes = await self._tcp_request(request, self.server_ip)

        response_body_str = response_body_bytes.decode("utf-8") #Peer IP Address

        if response_header.status == protocol.STATUS_OK:
            return response_body_str

        return "0.0.0.0"

<<<<<<< Updated upstream
        #TODO: Add error handling here?
=======
        
>>>>>>> Stashed changes

#---------------------------------------------------------------------------------------------------------------------
#P2P request and response methods
#---------------------------------------------------------------------------------------------------------------------

    #Requests file from peer and saves it if file transferred succesfully
    async def FILE_REQUEST(self, peer_ip: str, sha256_file_id: str, group_id: int, save_path: str) -> bool:

        request = protocol.FileRequest(
            version = MAP_VERSION,
            userID = self.AppState["user_id"],
            serverID = self.AppState["server_id"],
            type = "FILE_REQUEST",
            groupID = group_id,
            sha256 = sha256_file_id
        )

<<<<<<< Updated upstream
        response_header, response_body_bytes = await self._tcp_request(request, b"", peer_ip)
=======
        response_header, response_body_bytes = await self._tcp_request(
            request, peer_ip, b"", P2P_PORT
        )
>>>>>>> Stashed changes

        if response_header.status != protocol.STATUS_OK:
            return False
        
        #Verifying file integrity
        computed_hash = hashlib.sha256(response_body_bytes).hexdigest().upper()
<<<<<<< Updated upstream
        if computed_hash != sha256_file_id:
            return False
        
        # Write raw bytes directly to disk — no decoding needed
=======
        if computed_hash != sha256_file_id or response_header.length != len(response_body_bytes):
            return False 

        # Write raw bytes directly to disk
>>>>>>> Stashed changes
        with open(save_path, "wb") as f:
            f.write(response_body_bytes)
            
        return True
    
    #TODO:
    #def _handle_p2p_request(self, conn: socket.socket, addr):

<<<<<<< Updated upstream
=======
    
    async def _handle_p2p_request(self, sock: socket.socket, peer_ip):
        
        try:
            stream = protocol.MapStreamBuffer(sock)

            while True:
                header_bytes = await stream.read_header()
                print(f"> TCP received from {peer_ip}: {header_bytes}")

                response_body = None

                try:
                    
                    header = protocol.parse_request_header(header_bytes, self.AppState["server_id"])
                    
                    sha256 = header.sha256

                    #Look for shared file which matches sha256 hash of request
                    file_path = self.AppState["shared_files"].get(sha256)  # None if not found

                    #If file matching sha256 hash from request does exist and is shared, parse it
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

                #Send response header
                print(f"< P2P TCP sending to {peer_ip}: {response_json}\x03")
                sock.sendall(response_bytes)
                sock.sendall(b"\x03")

                #Send file (response body)
                if response_body:
                    print(f"< P2P TCP sending to {peer_ip}: {response_body}")
                    sock.sendall(response_body)

        except ConnectionError as _:
            pass
        finally:
            sock.close()
            print(f"TCP closed: {peer_ip}")
>>>>>>> Stashed changes


<<<<<<< Updated upstream
#---------------------------------------------------------------------------------------------------------------------
#Server communication
#---------------------------------------------------------------------------------------------------------------------

    #Creates and sends TCP request, and returns Response object (header of response), and response body
    #Default is TCP request to server, unless other IP is specified

    async def _tcp_request(self, header: protocol.BaseRequest, body: bytes = b"", ip_address = SERVER_IP) -> tuple[protocol.Response, Optional[bytes]]:

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((ip_address, TCP_PORT))
=======
    async def _tcp_request(
        self,
        header: protocol.BaseRequest,
        ip_address = default_server_ip,
        body: bytes = b"",
        port = TCP_PORT #Default port which server listens on
    ) -> tuple[protocol.Response, Optional[bytes]]:
        """
        Creates and sends TCP request, and returns Response object with response header and body.

        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((ip_address, port))
>>>>>>> Stashed changes

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
        response_header_json = response_header_bytes.decode("utf-8")
        response_header = protocol.parse_response_header(response_header_json)

        if isinstance(response_header, protocol.BodyResponse): #Generic response header doesn't have length field
            response_body_bytes = await stream.read_body(response_header.length)
        else:
            response_body_bytes = b""


        sock.close()
        return response_header, response_body_bytes

<<<<<<< Updated upstream
    #Sends UDP request, returns Response object. No request body or response body is accomodated for here
    #  as it is not needed
    def _udp_request(self, header: protocol.BaseRequest, ip_address = SERVER_IP) -> protocol.Response:
=======
    def _udp_request(
        self, header: protocol.BaseRequest,
    ) -> protocol.Response:
        """
        Sends UDP request, returns Response object.

        """

>>>>>>> Stashed changes
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        #Very important, otherwise hangs forever on sock.recvfrom(65535)
        sock.settimeout(ALIVE_TIMEOUT)

        #Build payload
        header_bytes = header.model_dump_json().encode("utf-8")

        #Send
        sock.sendto(header_bytes, (ip_address, UDP_PORT))

        #Receive response and parse
        try:
            print("Trying UDP")
            response_header_bytes, _ = sock.recvfrom(65535)
            print("Completed UDP")
            response_header_json = response_header_bytes.decode("utf-8")
            sock.close()
            return protocol.parse_response_header(response_header_json)
        except socket.timeout:
            print("[!] UDP request timed out")
            sock.close()
            return None
        
        

       
    #---------------------------------------------------------------------------------------------------------------------
    #TODO: Thread loops
    #---------------------------------------------------------------------------------------------------------------------

    def _listen_P2P(self):

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", P2P_PORT))
        server_sock.listen(10)

        print(f"Listening for P2P requests")

        while True:
<<<<<<< Updated upstream
            peer_sock, addr = server_sock.accept()
            #Handle each peer connection in another thread
            #so one slow transfer doesn't block others
            threading.Thread(
                target=self._handle_p2p_request,
                args=(peer_sock, addr),
                daemon=True
            ).start()
=======
            peer_sock, (peer_ip, peer_port) = server_sock.accept()
            run_async_in_thread(self._handle_p2p_request(peer_sock, peer_ip))

>>>>>>> Stashed changes

    def _im_alive_loop(self):
        
        while True:
            request = protocol.ImAlive(
                version=MAP_VERSION,
                userID=self.AppState["user_id"],
                serverID=self.AppState["server_id"],
                type="IM_ALIVE",
                localIP=self.local_ip,
                afterEventID=self.AppState["last_event_id"]
            )
            response = self._udp_request(request)
            print("IM ALIVE: ")

            if isinstance(response, protocol.ImAliveResponse) and response.isOutdated:
                
                events = asyncio.run(self.GET_EVENTS())
                for event in events:
                    if isinstance(event, protocol.MessageEvent):
                        print(f"[MSG] {event.senderUserID}: {event.message}")
                    elif isinstance(event, protocol.FileAvailableEvent):
                        print(f"[FILE] {event.senderUserID} shared {event.fileName}")
                    elif isinstance(event, protocol.AddMemberEvent):
                        print(f"[MEMBER] {event.userID} was added by {event.senderUserID}")
                  
                #tell TUI to fetch new events
               
            
            
            time.sleep(ALIVE_INTERVAL)



    #---------------------------------------------------------------------------------------------------------------------
    #Internal Helpers
    #---------------------------------------------------------------------------------------------------------------------

    #Obtain local IP so that user doesn't have to enter it
    @staticmethod
    def _get_local_ip() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # Doesn't actually send anything
            return s.getsockname()[0]
        finally:
            s.close()

    #-------------------------------------------------------------------------------------------------------------------------
async def main():
    c = Client()
    print(await c.login("Thomas", ""))
    time.sleep(7)
    await c.send_message(5, "Message Test 5")
    time.sleep(7)
    await c.send_message(5, "Message Test 6")
    for thread in threads:

        thread.join()
    print("[-] All threads finished.")

if __name__ == "__main__":
    asyncio.run(main())
