import json
import socket
import struct
import threading
import unittest

from protocol import (ConnectionClosed, ProtocolError, receive_exact,
                      receive_frame, send_frame, validate_file_offer,
                      validate_message)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = socket.socketpair()
        self.a.settimeout(2)
        self.b.settimeout(2)

    def tearDown(self):
        self.a.close()
        self.b.close()

    def test_one_frame(self):
        send_frame(self.a, {"type": "HELLO", "name": "Tiếng Việt", "size": 9})
        self.assertEqual(receive_frame(self.b)["name"], "Tiếng Việt")

    def test_multiple_frames_not_merged(self):
        send_frame(self.a, {"type": "BYE"})
        send_frame(self.a, {"type": "HELLO_ACK", "name": "B"})
        self.assertEqual(receive_frame(self.b)["type"], "BYE")
        self.assertEqual(receive_frame(self.b)["name"], "B")

    def test_fragmented_tcp_header_and_payload(self):
        body = json.dumps({"type": "MESSAGE", "size": 20}).encode()
        packet = struct.pack("!I", len(body)) + body
        def writer():
            for byte in packet:
                self.a.sendall(bytes([byte]))
        t = threading.Thread(target=writer)
        t.start()
        self.assertEqual(receive_frame(self.b)["size"], 20)
        t.join(2)

    def test_closed_early(self):
        self.a.sendall(b"ab")
        self.a.shutdown(socket.SHUT_WR)
        with self.assertRaises(ConnectionClosed):
            receive_exact(self.b, 4)

    def test_invalid_headers(self):
        self.a.sendall(struct.pack("!I", 20000))
        with self.assertRaises(ProtocolError):
            receive_frame(self.b)

    def test_invalid_filename(self):
        with self.assertRaises(ProtocolError):
            validate_file_offer({"type": "FILE_OFFER", "filename": "../../secret", "size": 12})
        with self.assertRaises(ProtocolError):
            validate_file_offer({"type": "FILE_OFFER", "filename": "a.txt", "size": -1})
        validate_file_offer({"type": "FILE_OFFER", "filename": "bài tập.pdf", "size": 0})

    def test_validate_message(self):
        validate_message("Xin chào 😀")
        with self.assertRaises(ValueError):
            validate_message("")
        with self.assertRaises(ValueError):
            validate_message("a" * (1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
