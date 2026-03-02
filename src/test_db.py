import asyncio
import db

async def main():

    await db.init_db()
    await db.create_group("Hello!")
    await db.create_membership(1, 16)
    await db.create_event(1, 16, "Hello - this is a message.", 1)
    server_id = await db.get_server_id()
    print(f"[+] Server ID is {server_id}")


if __name__ == "__main__":
    asyncio.run((main()))
