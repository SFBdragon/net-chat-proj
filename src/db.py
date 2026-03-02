import secrets
from typing import Iterable

import aiosqlite
from pydantic import BaseModel

import protocol

EVENT_TYPE_MESSAGE = 1
EVENT_TYPE_FILE_AVAILABILITY = 2
EVENT_TYPE_ADD_MEMBER = 3


class FileAvailabilityEventData(BaseModel):
    name: str
    sha256: str


db_name = "db.sqlite3"


async def init_db() -> str:

    try:
        with open(db_name, "r") as _:
            # file exists
            print("[+] Database exists. Skipping init.")
            pass

        async with aiosqlite.connect(db_name) as db:
            async with db.execute("SELECT serverID FROM server") as cursor:
                server_id = ""
                set_server_id = False
                async for row in cursor:
                    if set_server_id:
                        print("Bad database. There should only be one Server ID.")
                        exit(1)

                    server_id = row[0]
                    set_server_id = True

    except FileNotFoundError:
        async with aiosqlite.connect(db_name) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    eventID INTEGER PRIMARY KEY AUTOINCREMENT,
                    toGroupID INTEGER,
                    fromUserID TEXT,
                    eventData TEXT,
                    eventType INTEGER
                )
            """)
            await db.commit()

            await db.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    groupID INTEGER PRIMARY KEY AUTOINCREMENT,
                    groupName TEXT
                )
            """)
            await db.commit()

            await db.execute("""
                CREATE TABLE IF NOT EXISTS memberships (
                    groupID INTEGER,
                    userID TEXT,
                    PRIMARY KEY (groupID, userID)
                )
            """)
            await db.commit()

            # Generate random 16-character string
            base64_chars = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            )
            server_id = "".join(secrets.choice(base64_chars) for _ in range(16))

            await db.execute("""
                CREATE TABLE IF NOT EXISTS server (
                    serverID TEXT,
                    protocolVersion TEXT,
                    PRIMARY KEY (serverID)
                )
            """)
            await db.commit()

            await db.execute("INSERT INTO server(serverID) VALUES (?)", (server_id,))
            await db.commit()

    return server_id


async def create_event(
    to_group_id: int, from_user_id: str, event_data: str, event_type: int
) -> int:
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute(
            "INSERT INTO events(toGroupID, fromUserID, eventData, eventType) VALUES(?, ?, ?, ?)",
            (to_group_id, from_user_id, event_data, event_type),
        )
        await db.commit()

        if not cursor.lastrowid:
            raise Exception("Shouldn't happen.")
        return cursor.lastrowid


async def create_membership(group_id: int, user_id: str):
    async with aiosqlite.connect(db_name) as db:
        await db.execute(
            "INSERT OR IGNORE INTO memberships(groupID, userID) VALUES(?, ?)",
            (group_id, user_id),
        )
        await db.commit()


async def create_group(group_name: str) -> int:
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute(
            "INSERT INTO groups(groupName) VALUES(?)", (group_name,)
        )
        await db.commit()

        if not cursor.lastrowid:
            raise Exception("Shouldn't happen.")
        return cursor.lastrowid


async def get_server_id():
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute("SELECT serverID FROM server LIMIT 1")
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return row[0]
        else:
            return None


async def get_events(
    user_id: str,
    group_id: int | None,
    after_event_id: int | None = None,
    before_event_id: int | None = None,
) -> Iterable[protocol.Event] | None:

    def parse_event_row(row: aiosqlite.Row) -> protocol.Event:
        """Parse a database row into a typed Event.

        Row format: (eventID, toGroupID, fromUserID, eventData, eventType)
        """

        event_id, to_group_id, from_user_id, event_data, event_type = row

        if event_type == EVENT_TYPE_MESSAGE:
            return protocol.MessageEvent(
                eventID=event_id,
                senderUserID=from_user_id,
                type="SEND_MESSAGE",
                message=event_data,
            )
        elif event_type == EVENT_TYPE_FILE_AVAILABILITY:
            data = FileAvailabilityEventData.model_validate_json(event_data)
            return protocol.FileAvailableEvent(
                eventID=event_id,
                senderUserID=from_user_id,
                type="FILE_AVAILABLE",
                sha256=data.sha256,
                fileName=data.name,
            )
        elif event_type == EVENT_TYPE_ADD_MEMBER:
            return protocol.AddMemberEvent(
                eventID=event_id,
                senderUserID=from_user_id,
                type="ADD_MEMBER",
                userID=event_data,
            )
        else:
            raise ValueError(f"Unknown event type: {event_type}")

    async with aiosqlite.connect(db_name) as db:
        query_parts = ["SELECT * FROM events WHERE eventID > ?"]
        params: list = [after_event_id]

        if before_event_id:
            query_parts.append("AND eventID < ?")
            params.append(before_event_id)

        if group_id:
            query_parts.append("AND toGroupID = ?")
            params.append(group_id)
        else:
            query_parts.append("""AND toGroupID IN (
                SELECT groupID FROM memberships
                WHERE userID = ?
            )""")
            params.append(user_id)

        cursor = await db.execute(" ".join(query_parts), params)

        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return None

        [parse_event_row(row) for row in rows]


async def check_membership(user_id: str, group_id: int) -> bool:
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute(
            """
            SELECT * FROM memberships
            WHERE groupID == ?
            AND userID == ?
            """,
            (group_id, user_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return True
        else:
            return False


async def group_members(group_id: int) -> Iterable[str] | None:
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute(
            "SELECT userID FROM memberships WHERE groupID == ?",
            (group_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        map(lambda row: row[0], rows)
