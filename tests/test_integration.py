import hashlib
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest import mock

from cli import Console
from discovery import DiscoveryService
import file_transfer
from file_transfer import compute_sha256, receive_file
from tcp_chat import ChatNode


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for expected state")


class EndToEndIntegrationTests(unittest.TestCase):
    """Full-stack integration tests combining DiscoveryService, ChatNode, file_transfer, and Console."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src_dir = Path(self.tmp.name) / "src"
        self.downloads_dir = Path(self.tmp.name) / "downloads"
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        patcher = mock.patch.object(file_transfer, "DEFAULT_DOWNLOADS_DIR", self.downloads_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.alice = ChatNode("Alice", host="127.0.0.1", peer_id="alice-int")
        self.bob = ChatNode("Bob", host="127.0.0.1", peer_id="bob-int")
        self.alice.start()
        self.bob.start()
        self.addCleanup(self.alice.stop)
        self.addCleanup(self.bob.stop)

        # Register real file_transfer.receive_file exactly as main.py does.
        self.alice.register_file_handler(receive_file)
        self.bob.register_file_handler(receive_file)

        self.alice_disc = DiscoveryService(self.alice.peer_id, self.alice.name, self.alice.port)
        self.bob_disc = DiscoveryService(self.bob.peer_id, self.bob.name, self.bob.port)

        # Inject Bob into Alice's discovery table (same path as UDP _listen -> _observe).
        self.alice_disc._observe(
            (
                f'{{"type":"HELLO","version":1,"peer_id":"{self.bob.peer_id}",'
                f'"name":"{self.bob.name}","tcp_port":{self.bob.port},"status":"online"}}'
            ).encode("utf-8"),
            "127.0.0.1",
            time.monotonic(),
        )

        self.alice_lines = []
        self.bob_lines = []
        self.alice_lock = threading.Lock()
        self.bob_lock = threading.Lock()

        def alice_notice(msg):
            with self.alice_lock:
                self.alice_lines.append(msg)

        def bob_notice(msg):
            with self.bob_lock:
                self.bob_lines.append(msg)

        self.alice_console = Console(self.alice, self.alice_disc, alice_notice)
        self.bob_console = Console(self.bob, self.bob_disc, bob_notice)

    def _drain_console_events(self, node, console):
        while True:
            try:
                event = node.events.get_nowait()
            except queue.Empty:
                return
            console.show_chat_event(event)

    def test_cli_list_chat_real_file_send_throttled_progress_and_receiver_notice(self):
        # 1. Alice discovers Bob via /list and opens chat via /chat 1.
        self.assertTrue(self.alice_console.handle("/list"))
        self.assertTrue(self.alice_console.handle("/chat 1"))
        wait_for(lambda: len(self.bob.get_peers()) == 1)
        self.bob.activate_chat(self.alice.peer_id)

        # 2. Create a real 1.5 MiB binary file (~24 chunks of 64 KiB).
        src = self.src_dir / "báo cáo tích hợp.pdf"
        seed = hashlib.sha256(b"integration-e2e-seed").digest() * 2048  # 64 KiB
        payload = seed * 24 + b"END"
        src.write_bytes(payload)

        # 3. Alice sends the file via CLI using single-quoted path AND sends chat text.
        self.assertTrue(self.alice_console.handle(f"/send '{src}'"))
        self.assertTrue(self.alice_console.handle("Tin nhắn gửi ngay sau /send"))

        def alice_has(needle):
            with self.alice_lock:
                return any(needle in line for line in self.alice_lines)

        # Wait for sender 100% completion and receiver file_received event.
        wait_for(lambda: alice_has("100%"), timeout=10.0)

        def bob_got_file_and_msg():
            self._drain_console_events(self.bob, self.bob_console)
            with self.bob_lock:
                lines = list(self.bob_lines)
            has_file = any("[File from Alice]" in line and "báo cáo tích hợp.pdf" in line for line in lines)
            has_msg = any("Tin nhắn gửi ngay sau /send" in line for line in lines)
            return has_file and has_msg

        wait_for(bob_got_file_and_msg, timeout=10.0)

        # Verify byte-identical SHA-256 on disk.
        saved = self.downloads_dir / "báo cáo tích hợp.pdf"
        self.assertTrue(saved.is_file())
        self.assertEqual(compute_sha256(src), compute_sha256(saved))

        # Verify progress output was throttled (not 25+ spam lines).
        with self.alice_lock:
            progress_lines = [line for line in self.alice_lines if "báo cáo tích hợp.pdf" in line]
        self.assertLessEqual(len(progress_lines), 11)
        self.assertIn("100%", progress_lines[-1])

    def test_cli_duplicate_file_and_missing_file_error_recovery(self):
        self.alice_console.handle("/list")
        self.alice_console.handle("/chat 1")
        wait_for(lambda: len(self.bob.get_peers()) == 1)

        src = self.src_dir / "spec.bin"
        first_data = os.urandom(16 * 1024)
        second_data = os.urandom(16 * 1024)

        src.write_bytes(first_data)
        self.alice_console.handle(f'/send "{src}"')
        wait_for(lambda: (self.downloads_dir / "spec.bin").is_file(), timeout=5.0)

        src.write_bytes(second_data)
        self.alice_console.handle(f'/send "{src}"')
        wait_for(lambda: (self.downloads_dir / "spec (1).bin").is_file(), timeout=5.0)

        self.assertEqual((self.downloads_dir / "spec.bin").read_bytes(), first_data)
        self.assertEqual((self.downloads_dir / "spec (1).bin").read_bytes(), second_data)

        # Missing file must report error in CLI without crashing Alice or Bob.
        missing = self.src_dir / "does_not_exist.bin"
        self.alice_console.handle(f'/send "{missing}"')

        def alice_saw_error():
            with self.alice_lock:
                return any("File transfer failed:" in line for line in self.alice_lines)

        wait_for(alice_saw_error, timeout=5.0)
        self.assertTrue(self.alice.is_running)
        self.assertTrue(self.bob.is_running)
        self.alice_console.handle("Still connected after missing file")
        wait_for(lambda: len(self.bob.get_history(self.alice.peer_id)) == 1)


if __name__ == "__main__":
    unittest.main()
