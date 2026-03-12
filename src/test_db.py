import asyncio
import tempfile

import db


async def main():
    temp_db_file = tempfile.NamedTemporaryFile(
        suffix=".sqlite", mode="w", delete=False, delete_on_close=False
    )

    # Initialize the database
    server_id = db.init_db(temp_db_file.name)

    # Check server ID
    print(f"[+] Server ID is {server_id}")
    assert server_id.isalnum()
    assert len(server_id) == 16

    async with db.Database(temp_db_file.name) as conn:
        # Create groups
        await conn.create_group("group1")
        await conn.create_group("group2")
        await conn.create_group("group3")
        await conn.create_group("group4")

        # Define memberships
        # group1: user1(1), user2(2)
        # group2: user1(1), user3(3)
        # group3: user1(1), user2(2), user3(3)
        # group4: user4(4)
        memberships = [
            # group1 memberships
            (1, "user1"),  # user1 in group1
            (1, "user2"),  # user2 in group1
            # group2 memberships
            (2, "user1"),  # user1 in group2
            (2, "user3"),  # user3 in group2
            # group3 memberships
            (3, "user1"),  # user1 in group3
            (3, "user2"),  # user2 in group3
            (3, "user3"),  # user3 in group3
            # group4 memberships
            (4, "user4"),  # user4 in group4
        ]

        # Create all memberships
        for group_id, user_id in memberships:
            await conn.create_membership(group_id, user_id)
            print(f"[+] Created membership: group{group_id} <- {user_id}")

        messages = [
            # GROUP 1 (user1, user2 can see) - Messages 1-5
            (1, "user1", "G1: M1 user1 says hello to group1!", 1),
            (1, "user2", "G1: M2 user2 responds in group1", 1),
            (1, "user1", "G1: M3 user1 message 3/5", 1),
            (1, "user2", "G1: M4 user2 message 4/5", 1),
            (1, "user1", "G1: M5 user1 final message in group1", 1),
            # GROUP 2 (user1, user3 can see) - Messages 6-10
            (2, "user1", "G2: M1 user1 starts group2 chat", 1),
            (2, "user3", "G2: M2 user3 joins conversation", 1),
            (2, "user1", "G2: M3 user1 reply to user3", 1),
            (2, "user3", "G2: M4 user3 second message", 1),
            (2, "user1", "G2: M5 user1 wraps up group2", 1),
            # GROUP 3 (user1, user2, user3 can see) - Messages 11-17
            (3, "user1", "G3: M1 user1 announces to everyone", 1),
            (3, "user2", "G3: M2 user2 reacts to announcement", 1),
            (3, "user3", "G3: M3 user3 also responds", 1),
            (3, "user1", "G3: M4 user1 continues discussion", 1),
            (3, "user2", "G3: M5 user2 adds comment", 1),
            (3, "user3", "G3: M6 user3 final thought", 1),
            (3, "user1", "G3: M7 user1 summary message", 1),
            # GROUP 4 (user4 only) - Messages 18-20
            (4, "user4", "G4: M1 user4 solo message 1", 1),
            (4, "user4", "G4: M2 user4 solo message 2", 1),
            (4, "user4", "G4: M3 user4 solo message 3", 1),
        ]

        # Simulate events (20 message events)
        print("[+] Creating 20 test messages...")
        for group_id, user_id, message, event_type in messages:
            await conn.create_event(group_id, user_id, message, event_type)
            print(f"    {message}")

        print("\n[+] Testing get_event_updates for different users:")

        # Test user1 (sees groups 1,2,3 = 17 messages)
        print("\n-------------------------------------------")
        print("User1 (groups 1,2,3) - expects 17 events:")
        events1 = await conn.get_events("user1", None, None)
        print(f"Count: {len(events1)} events")
        print("-------------------------------------------")

        # Test user2 (sees groups 1,3 = 12 messages)
        print("\n-------------------------------------------")
        print("User2 (groups 1,3) - expects 12 events:")
        events2 = await conn.get_events("user2", None, None)
        print(f"Count: {len(events2)} events")
        print("-------------------------------------------")

        # Test user3 (sees groups 2,3 = 12 messages)
        print("\n-------------------------------------------")
        print("User3 (groups 2,3) - expects 12 events:")
        events3 = await conn.get_events("user3", None, None)
        print(f"Count: {len(events3)} events")
        print("-------------------------------------------")

        # Test user4 (sees only group4 = 3 messages)
        print("\n-------------------------------------------")
        print("User4 (group 4) - expects 2 events:")
        events4 = await conn.get_events("user4", None, 10)
        print(f"Count: {len(events4)} events")
        print("-------------------------------------------")


if __name__ == "__main__":
    asyncio.run((main()))
