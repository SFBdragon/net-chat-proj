"""
Test the functionality of protocol.py

Run with:
- uv run src/test_protocol.py
"""

import unittest

import protocol


class TestProtocol(unittest.TestCase):
    def round_trip_request_header(self):
        cases: list[protocol.Request] = [
            protocol.ImAlive(
                version="1.2",
                userID="dan",
                serverID="394075623",
                type="IM_ALIVE",
                localIP="1.2.3.4",
                afterEventID=None,
            ),
            protocol.GetEvents(
                version="1.2",
                userID="dan",
                serverID="394075623",
                type="GET_EVENTS",
                groupID=123,
                afterEventID=None,
                beforeEventID=None,
            ),
        ]

        for request in cases:
            request_json = request.model_dump_json()
            request_bytes = request_json.encode("utf-8")
            output = protocol.parse_request_header(request_bytes, "394075623")
            self.assertEqual(request, output)

    def round_trip_response_header(self):
        cases: list[protocol.Response] = [
            protocol.GenericResponse(
                version="1.2", serverID="01234598765", status="OK"
            ),
            protocol.ImAliveResponse(
                version="0.1", serverID="253", status="OK", isOutdated=True
            ),
        ]

        for response in cases:
            json_str = response.model_dump_json()
            output = protocol.parse_response_header(json_str)
            self.assertEqual(response, output)


if __name__ == "__main__":
    unittest.main()
