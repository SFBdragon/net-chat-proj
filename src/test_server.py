"""
Test the functionality of server.py

Run with:
- uv run src/test_server.py
"""

import unittest

import protocol
import server

LOCALHOST = "127.0.0.1"
UDP_PORT = 19492
TCP_PORT = 23452


class DebugServer:
    def __init__(self):
        import db

        db.db_name = "debug_db.sqlite3"

        self.tcp_thread = server.run_async_in_thread(
            server.tcp_server_raw(LOCALHOST, TCP_PORT)
        )
        self.udp_thread = server.run_async_in_thread(
            server.udp_server_raw(LOCALHOST, UDP_PORT)
        )


class TestServer(unittest.TestCase):
    def round_trip_request_header(self):
        s = DebugServer()

        self.assertEqual(s.tcp_thread.daemon, True)


if __name__ == "__main__":
    unittest.main()
