# ---------------------------------------------------------------------------------------
from textual.message import Message
import logging
logging.basicConfig(level=logging.DEBUG, filename="debug.log", format="%(asctime)s %(message)s ", datefmt="%H:%M:%S %d/%m/%Y",)

MOD_CODE = "[DTS] "

# Update passing

class DataUpdated(Message):
    def __init__(self):
        super().__init__()
        logging.debug(MOD_CODE + "[!] Data sync called.")

# ---------------------------------------------------------------------------------------
