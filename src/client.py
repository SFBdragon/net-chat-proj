import json
import socket
import threading
import map


MAP_VERSION = "0.0"
TCP_PORT = 3030
UDP_PORT = 3031
P2P_PORT = 3032
SERVER_IP = ""

ALIVE_INTERVAL = 2  # seconds between IM_ALIVE requests
ALIVE_TIMEOUT = 5
HEADER_BODY_DELIMITER = b"\x03"


class Client:

    
    

    def __init__(self): #TODO UI Callback function will be a parameter here

        self.local_ip = _get_local_ip()

        #Maintains state of client backend for the UI to reference when refreshing
        #only given values after succesful REGISTER
        self.AppState = none

        #Callback function
        #self.on_state_update = ui_refresh
        

#---------------------------------------------------------------------------------------------------------------------
#Public API for GUI
#---------------------------------------------------------------------------------------------------------------------


    #REGISTER request to server, called by GUI when login button pressed
    def login(self, user_id: str, server_id = "") -> str:

        #Header for REGISTER request
        request = map.Register(
        version="1.0",
        type="REGISTER",
        userID=user_id,
        serverID=server_id,
        )

        resp, _ = self._tcp_request(request)


        if(resp.status == map.STATUS_OK):

            #Only do this if registration was succesful, i.e. STATUS_OK
            self.AppState = {
            "user_id": user_id,
            "server_id": server_id,
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

        

    #TODO: Implement method to update TUI whenever AppState changes due to new messages etc.    
    def send_update(self):
        self.on_state_update("data1")

#---------------------------------------------------------------------------------------------------------------------
#Server communication 
#---------------------------------------------------------------------------------------------------------------------

    #Creates and sends TCP request to server, and returns Response object (header of response), and response body
    #TODO: Make thread safe, for if _im_alive_loop and TUI function call happen simultaneously
    def _tcp_request(self, header: map.BaseRequest, body: bytes = b"") -> tuple[map.Response, bytes]:

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect((SERVER_IP, TCP_PORT))

            # Build payload (serialise using JSON)
            header_bytes = header.model_dump_json().encode("utf-8")

            if body:
            
                payload = header_bytes + HEADER_BODY_DELIMITER + body
            else:
                payload = header_bytes
            
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)  # Signal we're done sending

        finally:
            sock.close()
            
        # Read the full response from the server
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)

        response_bytes = b"".join(chunks)

        response_header_bytes, response_body = map.split_header_and_body(response_bytes) #Split response header and body
        response_header = map.parse_response_header(response_header_bytes) #Create response object to return

        return response_header, response_body 
    
#---------------------------------------------------------------------------------------------------------------------
#TODO: Thread loops 
#---------------------------------------------------------------------------------------------------------------------

#def _listen_P2P():
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

if __name__ == "__main__":
   



