import aiosqlite
import asyncio

db_name = 'db.sqlite3'

async def init_db():

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

async def create_event(to_group_id, from_user_id, message_content, is_file):

    async with aiosqlite.connect(db_name) as db:
        await db.execute(f'''
            INSERT INTO events(toGroupID, fromUserID, eventData, eventType) VALUES({to_group_id}, {from_user_id}, "{message_content}", {is_file})
        ''')
        await db.commit()



async def create_membership(group_id, user_id):

    async with aiosqlite.connect(db_name) as db:
        await db.execute(f'''
            INSERT INTO memberships(groupID, userID) VALUES({group_id}, {user_id})
        ''')
        await db.commit()


async def create_group(group_name):

    async with aiosqlite.connect(db_name) as db:
        await db.execute(f'''
            INSERT INTO groups(groupName) VALUES("{group_name}")
        ''')
        await db.commit()

async def main():
    await init_db()
    await create_group("Hello!")
    await create_membership(1, 16)
    await create_event(1, 16, "Hello - this is a message.", 1)

asyncio.run((main()))
