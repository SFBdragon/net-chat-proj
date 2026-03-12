MOD_CODE = "TCL"

import asyncio
import hashlib
import logging
import os
import time

import protocol
from client import Client

# Test configuration
TEST_FILE_PATH = "test_file.txt"
TEST_FILE_CONTENT = b"Hello, this is a test file for P2P transfer."
DOWNLOAD_PATH = "downloaded_file.txt"
SERVER_IP = "127.0.0.1"


def get_group_id(client: Client) -> int:
    """Returns the first group_id from AppState."""
    groups = client.groups
    assert len(groups) > 0, "Client has no groups in AppState"
    return next(iter(groups.values())).id


def find_file_event(
    client: Client, group_id: int
) -> protocol.FileAvailableEvent | None:
    """Returns the first FileAvailableEvent in a given group, or None."""
    for event in client.events:
        if isinstance(event, protocol.FileAvailableEvent) and event.groupID == group_id:
            return event
    return None


async def main():

    # ------------------------------------------------------------------
    # 1. Create test file on disk
    # ------------------------------------------------------------------
    with open(TEST_FILE_PATH, "wb") as f:
        f.write(TEST_FILE_CONTENT)
    print(f"[*] Created test file: {TEST_FILE_PATH}")

    # ------------------------------------------------------------------
    # 2. Register both clients
    # ------------------------------------------------------------------
    c1 = Client(None, SERVER_IP)
    assert await c1.login("TestP2P1"), "c1 failed to login"
    print("[+] c1 logged in.")

    c2 = Client(None, SERVER_IP)
    assert await c2.login("TestP2P2"), "c2 failed to login"
    print("[+] c2 logged in.")

    # ------------------------------------------------------------------
    # 3. c1 creates a group containing both users
    # ------------------------------------------------------------------
    await c1.create_group("TestGrp", ["TestP2P1", "TestP2P2"])
    print("[+] Group created.")

    # Wait for the IM_ALIVE loop to register both clients as alive on the
    # server (required for GET_PEER to succeed — server rejects requests
    # for peers with no liveness entry within the last 5 seconds).
    print("[*] Waiting 5 s for liveness to be established…")
    await asyncio.sleep(5)

    # c2 fetches events so it learns the group_id via AddMemberEvents.
    await c2.update()
    print("[+] c2 fetched initial events.")

    # ------------------------------------------------------------------
    # 4. Point both clients at the shared group
    # ------------------------------------------------------------------
    group_id = get_group_id(c1)
    print(f"[*] Shared group_id = {group_id}")

    c1.current_group = group_id
    c2.current_group = group_id

    # ------------------------------------------------------------------
    # 5. c1 shares the file
    # ------------------------------------------------------------------
    assert await c1._share_file(TEST_FILE_PATH), "c1 failed to share file"
    print("[+] c1 shared file.")

    # ------------------------------------------------------------------
    # 6. c2 polls for the FileAvailableEvent
    # ------------------------------------------------------------------
    await asyncio.sleep(2)
    await c2.update()

    file_event = find_file_event(c2, group_id)
    assert file_event is not None, "c2 did not receive a FileAvailableEvent"
    print(
        f"[+] c2 received FileAvailableEvent: {file_event.fileName} ({file_event.sha256})"
    )

    # ------------------------------------------------------------------
    # 7. c2 downloads the file via get_file (resolves peer IP internally)
    # ------------------------------------------------------------------
    download_ok = await c2._get_file(
        peer_user_id="TestP2P1",
        sha256_file_id=file_event.sha256,
        save_path=DOWNLOAD_PATH,
    )
    assert download_ok, "get_file failed"
    print(f"[+] File downloaded to {DOWNLOAD_PATH}")

    # ------------------------------------------------------------------
    # 8. Verify content and hash
    # ------------------------------------------------------------------
    with open(DOWNLOAD_PATH, "rb") as f:
        downloaded_bytes = f.read()

    assert downloaded_bytes == TEST_FILE_CONTENT, (
        f"File content mismatch!\n"
        f"  Expected : {TEST_FILE_CONTENT}\n"
        f"  Got      : {downloaded_bytes}"
    )

    computed_hash = hashlib.sha256(downloaded_bytes).hexdigest().upper()
    assert computed_hash == file_event.sha256, (
        f"SHA-256 mismatch!\n"
        f"  Expected : {file_event.sha256}\n"
        f"  Got      : {computed_hash}"
    )

    print("\n✅  P2P file transfer test PASSED.")
    print(f"    Original  : {TEST_FILE_CONTENT}")
    print(f"    Downloaded: {downloaded_bytes}")
    print(f"    SHA-256   : {computed_hash}")


if __name__ == "__main__":
    asyncio.run(main())
