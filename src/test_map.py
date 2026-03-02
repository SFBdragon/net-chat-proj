"""
Test the functionality of map.py

Run with:
- uv run src/test_map.py
"""

import unittest

import map


class TestMAP(unittest.TestCase):
    def test_body_split(self):
        cases: list[tuple[bytes, tuple[bytes, bytes | None]]] = [
            (b"header", (b"header", None)),
            (b"header\x03body", (b"header", b"body")),
            (
                b'{ version: "1.0", userID: "ben", serverID: "1234567890", type: "REGISTER" }\r\n\x03\x00\x03\x03\x00',
                (
                    b'{ version: "1.0", userID: "ben", serverID: "1234567890", type: "REGISTER" }\r\n',
                    b"\x00\x03\x03\x00",
                ),
            ),
        ]

        for input, expected_output in cases:
            output = map.split_header_and_body(input)
            self.assertEqual(output, expected_output)

    def test_request_header_parse(self):
        cases: list[map.Request] = [
            map.ImAlive(
                version="1.2",
                userID="dan",
                serverID="394075623",
                type="IM_ALIVE",
                localIP="1.2.3.4",
                afterEventID=None,
            ),
            map.GetEvents(
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
            output = map.parse_request_header(request_bytes)
            self.assertEqual(request, output)

    def test_response_header_parse(self):
        cases: list[map.Response] = [
            map.GenericResponse(version="1.2", serverID="01234598765", status="OK"),
            map.ImAliveResponse(
                version="0.1", serverID="253", status="OK", isOutdated=True
            ),
        ]

        for response in cases:
            json_str = response.model_dump_json()
            output = map.parse_response_header(json_str)
            self.assertEqual(response, output)


if __name__ == "__main__":
    unittest.main()
