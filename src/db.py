import asyncio
import secrets
import aiosqlite

db_name = "db.sqlite3"

async def init_db():

    try:
        with open(db_name, 'r') as f:
            # file exists
            print("[+] Database exists. Skipping init.")
            pass
    except FileNotFoundError:
        async with aiosqlite.connect(db_name) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    eventID INTEGER PRIMARY KEY AUTOINCREMENT,
                    toGroupID INTEGER,
                    fromUserID INTEGER,
                    eventData TEXT,
                    eventType INTEGER
                )
            ''')
            await db.commit()

            await db.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    groupID INTEGER PRIMARY KEY AUTOINCREMENT,
                    groupName TEXT
                )
            ''')
            await db.commit()

            await db.execute('''
                CREATE TABLE IF NOT EXISTS memberships (
                    groupID INTEGER,
                    userID INTEGER,
                    PRIMARY KEY (groupID, userID)
                )
            ''')
            await db.commit()

            # Generate random 16-character string
            base64_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
            server_id = ''.join(secrets.choice(base64_chars) for _ in range(16))

            await db.execute('''
                CREATE TABLE IF NOT EXISTS server (
                    serverID TEXT,
                    protocolVersion TEXT,
                    PRIMARY KEY (serverID)
                )
            ''')
            await db.commit()

            await db.execute(f'''
                INSERT INTO server(serverID, protocolVersion) VALUES (?, ?)
            ''', (server_id, "1.0"))
            await db.commit()



async def create_event(to_group_id, from_user_id, message_content, is_file):

    async with aiosqlite.connect(db_name) as db:
        await db.execute(f'''
            INSERT INTO events(toGroupID, fromUserID, eventData, eventType) VALUES(?, ?, ?, ?)
        ''', (to_group_id, from_user_id, message_content, is_file))
        await db.commit()


async def create_membership(group_id, user_id):

    async with aiosqlite.connect(db_name) as db:
        await db.execute(f'''
            INSERT OR IGNORE INTO memberships(groupID, userID) VALUES(?, ?)
        ''', (group_id, user_id))
        await db.commit()


async def create_group(group_name):

    async with aiosqlite.connect(db_name) as db:
        await db.execute(f'''
            INSERT INTO groups(groupName) VALUES(?)
        ''', (group_name,))
        await db.commit()

async def get_server_id():
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute("SELECT serverID FROM server LIMIT 1")
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return row[0]
        else:
            return None

async def get_events(user_id, from_event_id=0, to_event_id=0):
    async with aiosqlite.connect(db_name) as db:

        event_upper_limit = ""
        if (to_event_id != 0):
            event_upper_limit = f"AND eventID < {to_event_id}"

        cursor = await db.execute(f'''
            SELECT * FROM events
            WHERE eventID > ?
            ''' + event_upper_limit + f'''
            AND toGroupID IN (
                SELECT groupID from memberships
                WHERE userID == ?
            )
        ''', (from_event_id, user_id))

        rows = await cursor.fetchall()
        await cursor.close()
        if rows:
            return rows
        else:
            return None

async def check_membership(user_id, group_id):
    async with aiosqlite.connect(db_name) as db:
        cursor = await db.execute(f'''
            SELECT * FROM memberships
            WHERE groupID == ?
            AND userID == ?
        ''', (group_id, user_id))
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return True
        else:
            return False



