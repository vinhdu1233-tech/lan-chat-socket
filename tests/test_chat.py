import socket
import threading
import time
import unittest

from protocol import receive_exact, receive_frame, send_frame
from tcp_chat import ChatNode


def wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for expected state")


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.a = ChatNode("Alice", host="127.0.0.1", peer_id="a")
        self.b = ChatNode("Bob", host="127.0.0.1", peer_id="b")
        self.c = ChatNode("Chi", host="127.0.0.1", peer_id="c")
        for node in (self.a, self.b, self.c):
            node.start()

    def tearDown(self):
        for node in (self.a, self.b, self.c):
            node.stop()

    def test_bidirectional_chat_and_history(self):
        self.a.connect("127.0.0.1", self.b.port)
        wait_for(lambda: len(self.b.get_peers()) == 1)
        self.a.activate_chat("b")
        self.b.activate_chat("a")
        self.a.send_message("b", "Chào Bob 👋")
        self.b.send_message("a", "Hello Alice")
        wait_for(lambda: len(self.a.get_history("b")) == 2)
        wait_for(lambda: len(self.b.get_history("a")) == 2)
        self.assertEqual([x.text for x in self.a.get_history("b")],
                         ["Chào Bob 👋", "Hello Alice"])
        self.assertEqual(self.a.unread_count("b"), 0)
        self.assertEqual(self.b.unread_count("a"), 0)

    def test_unread_messages_when_another_chat_is_active(self):
        self.b.connect("127.0.0.1", self.a.port)
        self.c.connect("127.0.0.1", self.a.port)
        wait_for(lambda: len(self.a.get_peers()) == 2)
        self.a.activate_chat("b")
        self.c.send_message("a", "Message 1")
        self.c.send_message("a", "Message 2")
        wait_for(lambda: self.a.unread_count("c") == 2)
        self.assertEqual(self.a.unread_count("b"), 0)
        msgs = self.a.activate_chat("c")
        self.assertEqual([x.text for x in msgs], ["Message 1", "Message 2"])
        self.assertEqual(self.a.unread_count("c"), 0)

    def test_large_message_is_not_truncated(self):
        self.b.connect("127.0.0.1", self.a.port)
        data = "Xin chào 😀 " * 3000
        self.b.send_message("a", data)
        wait_for(lambda: len(self.a.get_history("b")) == 1)
        self.assertEqual(self.a.get_history("b")[0].text, data)

    def test_leave_and_reconnect(self):
        self.a.connect("127.0.0.1", self.b.port)
        self.a.activate_chat("b")
        self.a.leave_chat()
        wait_for(lambda: len(self.b.get_peers()) == 0)
        self.assertEqual(self.a.get_peers(), [])
        self.a.connect("127.0.0.1", self.b.port)
        wait_for(lambda: len(self.b.get_peers()) == 1)
        self.assertEqual(self.a.get_peer("b").name, "Bob")

    def test_peer_exit_does_not_crash_other_peer(self):
        self.b.connect("127.0.0.1", self.a.port)
        wait_for(lambda: len(self.a.get_peers()) == 1)
        self.b.stop()
        wait_for(lambda: len(self.a.get_peers()) == 0)
        self.assertTrue(self.a.is_running)

    def test_connect_check_udp_peer_id(self):
        from protocol import ProtocolError
        with self.assertRaises(ProtocolError):
            self.b.connect("127.0.0.1", self.a.port, expected_peer_id="not-a")
        wait_for(lambda: len(self.a.get_peers()) == 0)

    def test_simultaneous_connections_do_not_duplicate(self):
        errors = []
        def go(from_node, target):
            try:
                from_node.connect("127.0.0.1", target.port)
            except (ConnectionError, KeyError, OSError) as exc:
                errors.append(exc)
        t1 = threading.Thread(target=go, args=(self.a, self.b))
        t2 = threading.Thread(target=go, args=(self.b, self.a))
        t1.start(); t2.start()
        t1.join(3); t2.join(3)
        wait_for(lambda: len(self.a.get_peers()) == 1 and len(self.b.get_peers()) == 1)
        self.a.send_message("b", "Ping")
        wait_for(lambda: len(self.b.get_history("a")) == 1)
        self.assertEqual(self.b.get_history("a")[0].text, "Ping")

    def test_independent_file_connection_dispatch(self):
        result = []
        ready = threading.Event()
        def file_handler(sock, header, addr):
            result.append((header["filename"], receive_exact(sock, header["size"]), addr[0]))
            ready.set()
        self.a.register_file_handler(file_handler)
        self.b.connect("127.0.0.1", self.a.port)
        sock = self.b.open_file_connection("a")
        try:
            payload = b"file-demo" * 1000
            send_frame(sock, {"type": "FILE_OFFER", "filename": "notes.txt", "size": len(payload)})
            sock.sendall(payload)
            self.assertTrue(ready.wait(2))
            self.assertEqual(result[0][1], payload)
        finally:
            sock.close()
        self.b.send_message("a", "After file")
        wait_for(lambda: len(self.a.get_history("b")) == 1)

    def test_file_without_handler_returns_error(self):
        s = socket.create_connection(("127.0.0.1", self.a.port), timeout=2)
        try:
            send_frame(s, {"type": "FILE_OFFER", "filename": "f.txt", "size": 0})
            self.assertEqual(receive_frame(s)["type"], "ERROR")
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
