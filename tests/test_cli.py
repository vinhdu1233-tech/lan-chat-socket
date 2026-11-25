import io
import threading
import types
import unittest
from unittest.mock import Mock, patch

from cli import Console, Terminal
from discovery import DiscoveryService, Peer
from tcp_chat import ChatEvent, ChatNode


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.node = Mock(spec=ChatNode)
        self.node.active_peer_id = "b"
        self.node.get_peers.return_value = []
        self.node.activate_chat.return_value = []
        self.discovery = Mock(spec=DiscoveryService)
        self.a = Peer("a", "Alex", "127.0.0.1", 5001, "online", 0)
        self.b = Peer("b", "Alex", "127.0.0.1", 5002, "away", 0)
        self.discovery.get_peers.return_value = [self.a, self.b]
        self.lines = []
        self.console = Console(self.node, self.discovery, self.lines.append)

    def test_discovered_list_duplicate_name_and_stable_numbers(self):
        self.console.handle("/list")
        self.assertEqual(self.lines[-1], "2. Alex (127.0.0.1:5002) away")
        self.console.handle("/chat Alex")
        self.assertIn("Several", self.lines[-1])
        self.discovery.get_peers.return_value = [self.b]
        self.console.handle("/chat 1")
        self.assertIn("unavailable", self.lines[-1])
        self.node.connect_to_peer.assert_not_called()
        self.console.handle("/chat 2")
        self.node.connect_to_peer.assert_called_once_with(self.b)
        self.node.activate_chat.assert_called_once_with("b")

    def test_connected_chat_history_and_unread(self):
        self.node.get_peers.return_value = [self.a]
        self.discovery.get_peers.return_value = [self.a]
        self.node.activate_chat.return_value = [types.SimpleNamespace(sender="Alex", text="hi")]
        self.node.unread_count.return_value = 2
        self.console.show_chat_event(ChatEvent("unread", "a", "Alex", "hi", 2))
        self.assertIn("2 unread", self.lines[-1])
        self.console.handle("/chat alex")
        self.assertEqual(self.lines[-1], "[Alex] hi")
        self.node.connect_to_peer.assert_not_called()

    def test_status_text_commands_and_recoverable_errors(self):
        self.console.handle("/status away")
        self.discovery.set_status.assert_called_once_with("away")
        self.console.handle(" hi ")
        self.node.send_message.assert_called_once_with("b", " hi ")
        self.console.handle("/leave")
        self.node.leave_chat.assert_called_once_with()
        self.console.handle("/help")
        self.assertIn("/chat", self.lines[-1])
        self.node.active_peer_id = None
        self.node.connect_to_peer.side_effect = OSError("offline")
        self.discovery.get_peers.return_value = [self.a]
        for cmd in ("/wrong", "/status invalid", "/chat", "/chat 0", "hi",
                    "/send x.txt", "/quit extra", "/chat Alex"):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.console.handle(cmd))
                self.assertTrue(self.lines[-1].startswith(("Invalid", "Error")))
        self.assertFalse(self.console.handle("/quit"))

    def test_send_delegates_and_chat_remains_available(self):
        started, release, finished = (threading.Event() for _ in range(3))
        args = []
        def send_file(node, peer, path, progress_cb):
            args.append((node, peer, path))
            started.set()
            release.wait(2)
            progress_cb(100)
            finished.set()
        with patch.dict("sys.modules", file_transfer=types.SimpleNamespace(send_file=send_file)):
            try:
                self.console.handle('/send "C:\\my files\\notes.pdf"')
                self.assertTrue(started.wait(1))
                self.console.handle("during transfer")
                self.node.send_message.assert_called_once_with("b", "during transfer")
            finally:
                release.set()
            self.assertTrue(finished.wait(1))
        self.assertEqual(args, [(self.node, "b", r"C:\my files\notes.pdf")])
        self.assertIn("100%", self.lines[-1])

    def test_incoming_event_redraws_and_preserves_editable_text(self):
        stream = io.StringIO()
        terminal = Terminal(stream, True)
        console = Console(self.node, self.discovery, terminal.notice)
        def keys():
            yield from "draft"
            worker = threading.Thread(target=console.show_chat_event,
                                      args=(ChatEvent("message", "a", "Alex", "hey"),))
            worker.start()
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertIn("[Alex] hey\n> draft", stream.getvalue())
            yield from "\x7fT!\r"
        self.assertEqual(terminal.read_line(keys().__next__), "drafT!")

    def test_send_throttles_progress_supports_single_quotes_and_shows_file_received(self):
        finished = threading.Event()
        received_args = []

        def fake_send_file(node, peer, path, progress_cb):
            received_args.append((node, peer, path))
            # Simulate 160 chunks (like a 10 MB file).
            progress_cb(0.0)
            for i in range(1, 160):
                progress_cb((i / 160) * 100.0)
            progress_cb(100.0)
            finished.set()

        with patch.dict("sys.modules", file_transfer=types.SimpleNamespace(send_file=fake_send_file)):
            self.console.handle("/send '/tmp/my folder/slides.pdf'")
            self.assertTrue(finished.wait(2.0))

        self.assertEqual(received_args, [(self.node, "b", "/tmp/my folder/slides.pdf")])
        progress_lines = [line for line in self.lines if "slides.pdf" in line]
        # Throttled to 10% buckets (0%, 10%, ..., 90%, 100% -> at most 11 lines instead of 161).
        self.assertLessEqual(len(progress_lines), 11)
        self.assertIn("100%", progress_lines[-1])

        self.console.show_chat_event(
            ChatEvent(
                "file_received",
                "a",
                "Alex",
                "Received file 'slides.pdf' (1024 bytes) -> downloads/slides.pdf",
            )
        )
        self.assertIn("[File from Alex]", self.lines[-1])
        self.assertIn("slides.pdf", self.lines[-1])
