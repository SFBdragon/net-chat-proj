import json
import socket
import threading
import protocol
import hashlib
from typing import Optional
import asyncio

MAP_VERSION = "1.0"
TCP_PORT = 3030
UDP_PORT = 3031
P2P_PORT = 3032
SERVER_IP = "127.0.0.1"

ALIVE_INTERVAL = 2  # seconds between IM_ALIVE requests
ALIVE_TIMEOUT = 5
HEADER_BODY_DELIMITER = b"\x03"

class Client:

    def __init__(self): #TODO UI Callback function will be a parameter here

        self.local_ip = _get_local_ip()

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
            threading.Thread(target=self._listen_p2p, daemon=True).start()
            #TODO: Start thread for IM_ALIVE
        
        return login_status

    #TODO:
    #def send_message(content: str) -> bool:

    #def create_group(group_name: str, user_ids: list[str]) -> bool:

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

    #Obtains IP Address of peer for P2P file sharing
    async def GET_PEER(self, peer_user_id: str) -> str:

        request = protocol.GetPeer(
            version = MAP_VERSION,userID = self.AppState["user_id"],
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
    #TODO: Make thread safe, for if _im_alive_loop and TUI function call happen simultaneously
    async def _tcp_request(self, header: protocol.BaseRequest, body: bytes = b"", ip_address = SERVER_IP) -> tuple[protocol.Response, Optional[bytes]]:

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((ip_address, TCP_PORT))

        # Build payload (serialise using JSON)
        header_bytes = header.model_dump_json().encode("utf-8")
        print(f"Header bytes is {header_bytes}")
        if body:
            payload = header_bytes + HEADER_BODY_DELIMITER + body
        else:
            payload = header_bytes + HEADER_BODY_DELIMITER 
        print(len(body))
        print("Sending payload")
        sock.sendall(payload)

        #Read server response using protocol.py methods
        MSB = protocol.MapStreamBuffer(sock)
        await MSB._recv_into_buffer()

        response_header_bytes = await MSB.read_header()
        response_header = protocol.parse_response_header(response_header_bytes)
        
        response_body = await MSB.read_body(len(body))

        print(response_header)
        print(response_body)

        return response_header, response_body

#---------------------------------------------------------------------------------------------------------------------
#TODO: Thread loops
#---------------------------------------------------------------------------------------------------------------------

def _listen_P2P():

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

#def _im_alive_loop():


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
    _listen_P2P()

if __name__ == "__main__":
    asyncio.run(main())
