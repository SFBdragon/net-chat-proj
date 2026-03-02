import asyncio
import db

async def main():

    # Initialize the database
    await db.init_db()
    
    # Verify server ID created
    server_id = await db.get_server_id()
    print(f"[+] Server ID is {server_id}")

    # Create groups
    await db.create_group("group1")
    await db.create_group("group2")
    await db.create_group("group3")
    await db.create_group("group4")
    
    # Create memberships
    await db.create_membership(1, 16)

    # Simulate events
    await db.create_event(1, 16, "Hello - this is a message.", 1)

    # Get event updates
    events = await db.get_event_updates(16, 0)
    print(f"[+] Events:\n{events}")


if __name__ == "__main__":
    asyncio.run((main()))
