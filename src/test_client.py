MOD_CODE = "TCL"

import asyncio
import logging 
import time 
from client import Client

async def main():
    logging.debug(MOD_CODE + "[+] Main function called.")
    c = Client()
    print(await c.login("Thomas", ""))
    time.sleep(7)
    await c.send_message(5, "Message Test 5")
    time.sleep(7)
    await c.send_message(5, "Message Test 6")

if __name__ == "__main__":
    asyncio.run(main())
