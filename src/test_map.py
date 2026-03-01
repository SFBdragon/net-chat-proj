"""Run with"""

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
            dummy_request_header(),
        ]

        for request in cases:
            json_str = request.json()
            output = map.parse_request_header(json_str)
            self.assertEqual(request, output)
        self.assertEqual(5 - 3, 2)


def dummy_request_header(
    version="1.2",
    user_id="alex",
    server_id="0123456789",
    local_ip="1.2.3.4",
    after_event_id=123,
) -> map.ImAlive:
    return map.ImAlive(
        version=version,
        userID=user_id,
        serverID=server_id,
        type="IM_ALIVE",
        localIP=local_ip,
        afterEventID=after_event_id,
    )


if __name__ == "__main__":
    unittest.main()
