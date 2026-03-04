import json
import socket
import threading
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

# Lock to protect AppState modifications
appStateLock = threading.Lock()
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

        login_status = await self._REGISTER(user_id, server_id)

        if login_status == True:
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

        response_header, _ = await self._tcp_request(request, message_body)

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
        
        response_header, _ = await self._tcp_request(request)

        if(response_header.status == protocol.STATUS_OK):
            print(f"[+] Created group {group_name} successfully.")

    #TODO
    #def add_to_group(user_ids: list[str]) -> bool:

    #Obtains file from peer and writes to disk, returns True if succesful and False if not
    def get_file(self, peer_user_id: str, sha256_file_id: str, save_path: str) -> bool:

        group_id = self.AppState["current_group"] 
        peer_ip = self.GET_PEER(peer_user_id)

        return self.FILE_REQUEST(peer_ip, sha256_file_id,group_id, save_path)
    #def share_file(content: bytes = b"") -> bool:


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

        request = protocol.Register(
        version= MAP_VERSION,
        type="REGISTER",
        userID=user_id,
        serverID=server_id
        )

        response_header, _ = await self._tcp_request(request)


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


    #Returns all events after the latest eventID as a list of protocol.Event objects
    #TODO: Testing
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

        _, response_body_bytes = await self._tcp_request(request)
        
        response_body_json = response_body_bytes.decode("utf-8")
        response_body_list = protocol.parse_events_response_body(response_body_json)

        #Set last event ID to the last event in the returned list

        self.AppState["last_event_id"] = response_body_list[-1].eventID

        return response_body_list

    #Obtains IP Address of peer for P2P file sharing
    async def GET_PEER(self, peer_user_id: str) -> str:

        request = protocol.GetPeer(
            version = MAP_VERSION,
            userID = self.AppState["user_id"],
            serverID = self.AppState["server_id"],
            type = "GET_PEER",
            peerUserID = peer_user_id,
            groupID = self.AppState["current_group"]
        )

        response_header, response_body_bytes = await self._tcp_request(request)

        response_body_str = response_body_bytes.decode("utf-8") #Peer IP Address

        if response_header.status == protocol.STATUS_OK:
            return response_body_str

        return "0.0.0.0"

        #TODO: Add error handling here?

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

        response_header, response_body_bytes = await self._tcp_request(request, b"", peer_ip)

        if response_header.status != protocol.STATUS_OK:
            return False
        
        #Verifying file integrity
        computed_hash = hashlib.sha256(response_body_bytes).hexdigest().upper()
        if computed_hash != sha256_file_id:
            return False
        
        # Write raw bytes directly to disk — no decoding needed
        with open(save_path, "wb") as f:
            f.write(response_body_bytes)
            
        return True
    
    #TODO:
    #def _handle_p2p_request(self, conn: socket.socket, addr):



#---------------------------------------------------------------------------------------------------------------------
#Server communication
#---------------------------------------------------------------------------------------------------------------------

    #Creates and sends TCP request, and returns Response object (header of response), and response body
    #Default is TCP request to server, unless other IP is specified

    async def _tcp_request(self, header: protocol.BaseRequest, body: bytes = b"", ip_address = SERVER_IP) -> tuple[protocol.Response, Optional[bytes]]:

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((ip_address, TCP_PORT))

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

    #Sends UDP request, returns Response object. No request body or response body is accomodated for here
    #  as it is not needed
    def _udp_request(self, header: protocol.BaseRequest, ip_address = SERVER_IP) -> protocol.Response:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        

        #Build payload
        header_bytes = header.model_dump_json().encode("utf-8")

        #Send
        sock.sendto(header_bytes, (ip_address, UDP_PORT))

        #Receive response and parse
        response_header_bytes, _ = sock.recvfrom(65535)
        response_header_json = response_header_bytes.decode("utf-8")
        response_header = protocol.parse_response_header(response_header_json)

        sock.close()

        return response_header
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
            peer_sock, addr = server_sock.accept()
            #Handle each peer connection in another thread
            #so one slow transfer doesn't block others
            threading.Thread(
                target=self._handle_p2p_request,
                args=(peer_sock, addr),
                daemon=True
            ).start()

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
            
            if isinstance(response, protocol.ImAliveResponse) and response.isOutdated:

                print("IM ALIVE: ")

                #Quick, flimsy test

                """ 
                events = asyncio.run(self.GET_EVENTS())
                for event in events:
                    if isinstance(event, protocol.MessageEvent):
                        print(f"[MSG] {event.senderUserID}: {event.message}")
                    elif isinstance(event, protocol.FileAvailableEvent):
                        print(f"[FILE] {event.senderUserID} shared {event.fileName}")
                    elif isinstance(event, protocol.AddMemberEvent):
                        print(f"[MEMBER] {event.userID} was added by {event.senderUserID}")
                """    
                
                #call GET_EVENTS
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
    await c.create_group("MyGroup", ["Thomas",])
    await c.send_message(5, "Messaging works!")
    for thread in threads:
        thread.join()
    print("[-] All threads finished.")

if __name__ == "__main__":
    asyncio.run(main())
