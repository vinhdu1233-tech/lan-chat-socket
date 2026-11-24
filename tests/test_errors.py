import errno
import hashlib
import os
from pathlib import Path
import queue
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

import file_transfer
from file_transfer import (
    CHUNK_SIZE,
    compute_sha256,
    receive_file,
    send_file,
    send_file_async,
)
from protocol import ConnectionClosed, MAX_FILE_BYTES, ProtocolError, send_frame
from tcp_chat import ChatNode


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for expected state")


class FileTransferErrorAndReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src_dir = Path(self.tmp.name) / "src"
        self.downloads_dir = Path(self.tmp.name) / "downloads"
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        self.alice = ChatNode("Alice", host="127.0.0.1", peer_id="alice-err")
        self.bob = ChatNode("Bob", host="127.0.0.1", peer_id="bob-err")
        self.alice.start()
        self.bob.start()
        self.addCleanup(self.alice.stop)
        self.addCleanup(self.bob.stop)

        self.alice.connect("127.0.0.1", self.bob.port)
        wait_for(lambda: len(self.bob.get_peers()) == 1)

    def _drain_events(self, node):
        events = []
        while True:
            try:
                events.append(node.events.get_nowait())
            except queue.Empty:
                return events

    def test_nonexistent_source_path(self):
        missing = self.src_dir / "does_not_exist.pdf"
        with mock.patch.object(self.alice, "open_file_connection") as spy:
            with self.assertRaises(FileNotFoundError):
                send_file(self.alice, "bob-err", missing)
            spy.assert_not_called()

    def test_invalid_source_path(self):
        with mock.patch.object(self.alice, "open_file_connection") as spy:
            for invalid in ("", "   ", None, 123, "bad\x00path.txt"):
                with self.subTest(path=invalid):
                    with self.assertRaises(ValueError):
                        send_file(self.alice, "bob-err", invalid)  # type: ignore[arg-type]

            with self.assertRaises(IsADirectoryError):
                send_file(self.alice, "bob-err", self.src_dir)

            spy.assert_not_called()

    def test_permission_denied_on_source_file(self):
        src = self.src_dir / "protected.txt"
        src.write_bytes(b"secret")
        with mock.patch.object(self.alice, "open_file_connection") as spy:
            with mock.patch("builtins.open", side_effect=PermissionError("access denied")):
                with self.assertRaises(PermissionError):
                    send_file(self.alice, "bob-err", src)
            spy.assert_not_called()

    def test_invalid_filename_rejected(self):
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)

        invalid_names = [
            "",
            "   ",
            ".",
            "..",
            "bad\x00name.txt",
            "bad\nname.txt",
            "bad:name.txt",
            "bad*name.txt",
            "CON.txt",
            "NUL",
            "trailing_dot.",
            "trailing_space ",
            "a" * 256,
            12345,
            None,
        ]
        for bad_name in invalid_names:
            with self.subTest(filename=bad_name):
                header = {"type": "FILE_OFFER", "filename": bad_name, "size": 0}
                with self.assertRaises(ProtocolError):
                    receive_file(
                        s_recv, header, ("127.0.0.1", 50000), downloads_dir=self.downloads_dir
                    )
        self.assertEqual(list(self.downloads_dir.iterdir()), [])

    def test_path_traversal_attempt_rejected(self):
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)

        traversal_names = [
            "../outside.txt",
            "../../etc/passwd",
            "..\\outside.txt",
            "subdir/nested.txt",
            "subdir\\nested.txt",
            "/etc/passwd",
            "\\Windows\\System32\\evil.dll",
            "C:\\Windows\\evil.exe",
            "C:relative_drive.txt",
        ]
        for bad_name in traversal_names:
            with self.subTest(filename=bad_name):
                header = {"type": "FILE_OFFER", "filename": bad_name, "size": 5}
                with self.assertRaises(ProtocolError):
                    receive_file(
                        s_recv, header, ("127.0.0.1", 50000), downloads_dir=self.downloads_dir
                    )

        self.assertEqual(list(self.downloads_dir.iterdir()), [])
        self.assertFalse((self.downloads_dir.parent / "outside.txt").exists())

    def test_invalid_or_negative_advertised_file_size(self):
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)

        invalid_sizes = [-1, -999999, "100", 12.5, True, False, None, MAX_FILE_BYTES + 1]
        for bad_size in invalid_sizes:
            with self.subTest(size=bad_size):
                header = {"type": "FILE_OFFER", "filename": "valid.bin", "size": bad_size}
                with self.assertRaises(ProtocolError):
                    receive_file(
                        s_recv, header, ("127.0.0.1", 50000), downloads_dir=self.downloads_dir
                    )
        self.assertEqual(list(self.downloads_dir.iterdir()), [])

    def test_abrupt_sender_disconnect_cleans_up_partial_and_keeps_node_alive(self):
        self._drain_events(self.bob)
        handler_failed = threading.Event()

        def handler(sock, header, address):
            try:
                receive_file(sock, header, address, downloads_dir=self.downloads_dir, timeout=2.0)
            except Exception:
                handler_failed.set()
                raise

        self.bob.register_file_handler(handler)

        sock = self.alice.open_file_connection("bob-err")
        try:
            send_frame(
                sock,
                {
                    "type": "FILE_OFFER",
                    "sender_id": "alice-err",
                    "filename": "interrupted.bin",
                    "size": 256 * 1024,
                },
            )
            sock.sendall(b"X" * (32 * 1024))
        finally:
            sock.close()

        self.assertTrue(handler_failed.wait(5.0))
        wait_for(
            lambda: any(e.kind == "error" for e in self._drain_events(self.bob)),
            timeout=3.0,
        )

        # No partial (.part) or corrupted final file remains.
        self.assertEqual(list(self.downloads_dir.iterdir()), [])
        # ChatNode remains completely operational.
        self.assertTrue(self.bob.is_running)
        self.alice.send_message("bob-err", "Still alive after abrupt disconnect")
        wait_for(lambda: len(self.bob.get_history("alice-err")) == 1)
        self.assertEqual(
            self.bob.get_history("alice-err")[0].text,
            "Still alive after abrupt disconnect",
        )

    def test_incomplete_payload_removes_partial_and_preserves_existing_file(self):
        existing = self.downloads_dir / "important.bin"
        original_content = b"ORIGINAL_VALID_DATA"
        existing.write_bytes(original_content)

        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)

        header = {"type": "FILE_OFFER", "filename": "important.bin", "size": 10000}

        def partial_sender():
            s_send.sendall(b"partial-data-only")
            s_send.shutdown(socket.SHUT_WR)

        writer = threading.Thread(target=partial_sender)
        writer.start()

        with self.assertRaises(ConnectionClosed):
            receive_file(
                s_recv, header, ("127.0.0.1", 50000), downloads_dir=self.downloads_dir, timeout=2.0
            )
        writer.join(timeout=5.0)

        # Only the untouched original file should exist; no .part or duplicate file.
        files = list(self.downloads_dir.iterdir())
        self.assertEqual(files, [existing])
        self.assertEqual(existing.read_bytes(), original_content)

    def test_socket_timeout_cleans_up_partial_without_changing_global_timeout(self):
        previous_default = socket.getdefaulttimeout()
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)

        header = {"type": "FILE_OFFER", "filename": "stalled.bin", "size": 4096}
        # Send only a few bytes, then stall with socket open.
        s_send.sendall(b"stalled-prefix")

        with self.assertRaises((TimeoutError, socket.timeout)):
            receive_file(
                s_recv,
                header,
                ("127.0.0.1", 50000),
                downloads_dir=self.downloads_dir,
                timeout=0.15,
            )

        self.assertEqual(socket.getdefaulttimeout(), previous_default)
        self.assertEqual(list(self.downloads_dir.iterdir()), [])

    def test_write_failure_removes_partial_and_leaves_no_corrupt_final_file(self):
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)

        payload = b"D" * (CHUNK_SIZE * 2)
        header = {"type": "FILE_OFFER", "filename": "diskfull.bin", "size": len(payload)}

        def writer():
            try:
                s_send.sendall(payload)
            except OSError:
                pass

        sender_thread = threading.Thread(target=writer)
        sender_thread.start()

        real_ntf = tempfile.NamedTemporaryFile

        class FailingTempFile:
            def __init__(self, wrapped):
                self._wrapped = wrapped
                self.name = wrapped.name
                self._writes = 0

            def write(self, data):
                self._writes += 1
                if self._writes == 2:
                    raise OSError(errno.ENOSPC, "No space left on device")
                return self._wrapped.write(data)

            def flush(self):
                return self._wrapped.flush()

            def close(self):
                return self._wrapped.close()

        def failing_ntf(*args, **kwargs):
            return FailingTempFile(real_ntf(*args, **kwargs))

        with mock.patch.object(file_transfer.tempfile, "NamedTemporaryFile", side_effect=failing_ntf):
            with self.assertRaises(OSError) as ctx:
                receive_file(
                    s_recv,
                    header,
                    ("127.0.0.1", 50000),
                    downloads_dir=self.downloads_dir,
                    timeout=2.0,
                )

        self.assertEqual(ctx.exception.errno, errno.ENOSPC)
        s_recv.close()
        sender_thread.join(timeout=5.0)
        self.assertEqual(list(self.downloads_dir.iterdir()), [])

    def test_connection_refused_and_reset_never_report_100_percent(self):
        src = self.src_dir / "payload.bin"
        src.write_bytes(b"Z" * (CHUNK_SIZE * 4))

        # 1. Connection refused.
        progress_refused = []
        with mock.patch.object(
            self.alice,
            "open_file_connection",
            side_effect=ConnectionRefusedError("connection refused"),
        ):
            with self.assertRaises(ConnectionRefusedError):
                send_file(self.alice, "bob-err", src, progress_cb=progress_refused.append)
        self.assertNotIn(100.0, progress_refused)

        # 2. Connection reset mid-send.
        fake_sock = mock.Mock(spec=socket.socket)
        call_count = {"n": 0}

        def sendall_fail_midway(data):
            call_count["n"] += 1
            # First call is FILE_OFFER frame; second is chunk 1; fail on chunk 2.
            if call_count["n"] >= 3:
                raise ConnectionResetError("connection reset by peer")

        fake_sock.sendall.side_effect = sendall_fail_midway
        progress_reset = []

        with mock.patch.object(self.alice, "open_file_connection", return_value=fake_sock):
            with self.assertRaises(ConnectionResetError):
                send_file(self.alice, "bob-err", src, progress_cb=progress_reset.append)

        fake_sock.close.assert_called_once()
        self.assertNotIn(100.0, progress_reset)

    def test_send_file_async_captures_error_and_does_not_crash_node(self):
        self._drain_events(self.alice)
        captured_errors = []
        missing = self.src_dir / "missing_async.bin"

        task = send_file_async(
            self.alice,
            "bob-err",
            missing,
            on_error=captured_errors.append,
        )

        self.assertTrue(task.join(timeout=5.0))
        self.assertIsInstance(task.error, FileNotFoundError)
        self.assertEqual(len(captured_errors), 1)
        self.assertIsInstance(captured_errors[0], FileNotFoundError)

        with self.assertRaises(FileNotFoundError):
            task.get_result(timeout=1.0)

        wait_for(
            lambda: any(e.kind == "error" for e in self._drain_events(self.alice)),
            timeout=2.0,
        )
        self.assertTrue(self.alice.is_running)

    def test_concurrent_chat_activity_during_file_transfer_and_sha256_integrity(self):
        """Verify chat remains responsive mid-transfer and SHA-256 matches exactly."""
        src = self.src_dir / "concurrent_media.bin"
        # 2 MiB deterministic binary file (32 chunks of 64 KiB).
        seed = hashlib.sha256(b"concurrent-chat-file-test").digest() * 2048  # 64 KiB
        payload = seed * 32
        src.write_bytes(payload)

        first_chunk_received = threading.Event()
        allow_transfer_finish = threading.Event()
        receiver_done = threading.Event()
        saved_holder = []

        def gated_receiver_progress(pct):
            if pct > 0.0 and not first_chunk_received.is_set():
                first_chunk_received.set()
                # Hold the file receiver thread open until chat messages succeed.
                if not allow_transfer_finish.wait(timeout=5.0):
                    raise TimeoutError("test gate did not release")

        def bob_file_handler(sock, header, address):
            try:
                saved = receive_file(
                    sock,
                    header,
                    address,
                    downloads_dir=self.downloads_dir,
                    progress_cb=gated_receiver_progress,
                    timeout=5.0,
                )
                saved_holder.append(saved)
            finally:
                receiver_done.set()

        self.bob.register_file_handler(bob_file_handler)

        self.alice.activate_chat("bob-err")
        self.bob.activate_chat("alice-err")

        sender_progress = []
        task = send_file_async(
            self.alice,
            "bob-err",
            src,
            progress_cb=sender_progress.append,
        )

        # Wait deterministically until file transfer is actively in progress.
        self.assertTrue(first_chunk_received.wait(timeout=5.0))
        self.assertFalse(receiver_done.is_set())

        # Exchange bidirectional chat messages WHILE the file transfer is mid-flight!
        # Wait for each turn to arrive before the next reply so history order is deterministic across OSes.
        self.alice.send_message("bob-err", "Tin nhắn trong lúc gửi file #1")
        wait_for(lambda: len(self.bob.get_history("alice-err")) == 1)
        self.bob.send_message("alice-err", "Bob vẫn nhận và trả lời bình thường!")
        wait_for(lambda: len(self.alice.get_history("bob-err")) == 2)
        self.alice.send_message("bob-err", "Tin nhắn trong lúc gửi file #2")

        wait_for(lambda: len(self.bob.get_history("alice-err")) == 3)
        wait_for(lambda: len(self.alice.get_history("bob-err")) == 3)
        self.assertEqual(
            [m.text for m in self.bob.get_history("alice-err")],
            [
                "Tin nhắn trong lúc gửi file #1",
                "Bob vẫn nhận và trả lời bình thường!",
                "Tin nhắn trong lúc gửi file #2",
            ],
        )

        # Release the transfer gate and verify clean completion + SHA-256 checksum.
        allow_transfer_finish.set()
        result = task.get_result(timeout=10.0)
        self.assertTrue(receiver_done.wait(timeout=10.0))

        self.assertEqual(result.bytes_transferred, len(payload))
        self.assertEqual(sender_progress[-1], 100.0)
        self.assertEqual(len(saved_holder), 1)

        src_sha256 = compute_sha256(src)
        dst_sha256 = compute_sha256(saved_holder[0])
        self.assertEqual(src_sha256, dst_sha256)
        self.assertEqual(src_sha256, hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    unittest.main()
