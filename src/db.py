# ---------------------------------------------------------------------------------------

# Standard modules
from __future__ import annotations
from typing import Iterable
from pydantic import BaseModel
import secrets
import aiosqlite

# Custom Modules
import protocol

# Event definitions
EVENT_TYPE_MESSAGE = 1
EVENT_TYPE_FILE_AVAILABILITY = 2
EVENT_TYPE_ADD_MEMBER = 3


class FileAvailabilityEventData(BaseModel):
    name: str
    sha256: str


def init_db(db_path: str) -> str:
    """
    Creates tables and generates server ID.

    :param db_path: Path of database file.
    """
    import sqlite3

    with sqlite3.connect(db_path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                eventID INTEGER PRIMARY KEY AUTOINCREMENT,
                toGroupID INTEGER,
                fromUserID TEXT,
                eventData TEXT,
                eventType INTEGER
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                groupID INTEGER PRIMARY KEY AUTOINCREMENT,
                groupName TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS memberships (
                groupID INTEGER,
                userID TEXT,
                PRIMARY KEY (groupID, userID)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS server (
                serverID TEXT,
                PRIMARY KEY (serverID)
            )
        """)

        db.commit()

        cursor = db.execute("SELECT serverID from server")
        rows = list(cursor.fetchall())
        cursor.close()

        if len(rows) == 0:
            # No row exists, insert one
            #
            # Generate random 16-character string
            base64_chars = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            )
            server_id = "".join(secrets.choice(base64_chars) for _ in range(16))

            db.execute("INSERT INTO server (serverID) VALUES (?)", (server_id,))
            db.commit()
        elif len(rows) == 1:
            # Use the existing server ID
            server_id = str(rows[0][0])
        else:
            raise ValueError("Invalid database: Two or more server ID entries found.")

        return server_id


class Database:
    def __init__(self, db_path: str):
        """
        Set database file path and initialize async io connection.
        """
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self) -> DatabaseConnection:
        self._connection = await aiosqlite.connect(self.db_path)
        return DatabaseConnection(self._connection)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._connection:
            await self._connection.close()
        return False


class DatabaseConnection:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def create_event(
        self, to_group_id: int, from_user_id: str, event_data: str, event_type: int
    ) -> int:
        """
        Creates event by inserting into events table.
        """
        cursor = await self.db.execute(
            "INSERT INTO events(toGroupID, fromUserID, eventData, eventType) VALUES(?, ?, ?, ?)",
            (to_group_id, from_user_id, event_data, event_type),
        )
        await self.db.commit()

        if not cursor.lastrowid:
            raise Exception("Shouldn't happen.")
        return cursor.lastrowid

    async def create_membership(self, group_id: int, user_id: str):
        """
        Creates member by inserting into memberships table.
        """
        await self.db.execute(
            "INSERT OR IGNORE INTO memberships(groupID, userID) VALUES(?, ?)",
            (group_id, user_id),
        )
        await self.db.commit()

    async def create_group(self, group_name: str) -> int:
        """
        Creates group by inserting into groups table.
        """
        cursor = await self.db.execute(
            "INSERT INTO groups(groupName) VALUES(?)", (group_name,)
        )
        await self.db.commit()

        if not cursor.lastrowid:
            raise Exception("Shouldn't happen.")
        return cursor.lastrowid

    async def get_events(
        self,
        user_id: str,
        group_id: int | None,
        after_event_id: int | None,
        before_event_id: int | None = None,
    ) -> Iterable[protocol.Event] | None:

        async def parse_event_row(row: aiosqlite.Row) -> protocol.Event:
            """
            Parse a database row into a typed Event.
            Row format: (eventID, toGroupID, fromUserID, eventData, eventType)
            """

            event_id, to_group_id, from_user_id, event_data, event_type = row

            if event_type == EVENT_TYPE_MESSAGE:
                return protocol.MessageEvent(
                    eventID=event_id,
                    groupID=to_group_id,
                    senderUserID=from_user_id,
                    type="SEND_MESSAGE",
                    message=event_data,
                )
            elif event_type == EVENT_TYPE_FILE_AVAILABILITY:
                data = FileAvailabilityEventData.model_validate_json(event_data)
                return protocol.FileAvailableEvent(
                    eventID=event_id,
                    groupID=to_group_id,
                    senderUserID=from_user_id,
                    type="FILE_AVAILABLE",
                    sha256=data.sha256,
                    fileName=data.name,
                )
            elif event_type == EVENT_TYPE_ADD_MEMBER:
                cursor = await self.db.execute(
                    "SELECT groupName FROM groups WHERE groupID = ?", (to_group_id,)
                )
                await self.db.commit()

                group_name_row = await cursor.fetchone()
                if not group_name_row:
                    raise

                return protocol.AddMemberEvent(
                    eventID=event_id,
                    groupID=to_group_id,
                    senderUserID=from_user_id,
                    type="ADD_MEMBER",
                    userID=event_data,
                    groupName=group_name_row[0],
                )
            else:
                raise ValueError(f"Unknown event type: {event_type}")

        query_parts = ["SELECT * FROM events WHERE eventID > ?"]
        params: list = [after_event_id or 0]

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

        cursor = await self.db.execute(" ".join(query_parts), params)
        await self.db.commit()

        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return None

        return [await parse_event_row(row) for row in rows]

    async def check_membership(self, user_id: str, group_id: int) -> bool:
        """
        Checks if a user is a member of a particular group.
        """
        print(f"Checking for membership in {group_id} for {user_id}")
        async with self.db.execute(
            "SELECT * FROM memberships WHERE groupID == ? AND userID == ?",
            (group_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            print(f"Got row {row}")
            if row:
                print("Returns True")
                return True
            else:
                print("Returns False")
                return False

    async def group_members(self, group_id: int) -> Iterable[str] | None:
        """
        Gets all groups which a user is a member of.
        """
        async with self.db.execute(
            "SELECT userID FROM memberships WHERE groupID == ?",
            (group_id),
        ) as cursor:
            rows = await cursor.fetchall()

        map(lambda row: row[0], rows)
