import hashlib
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
import uuid
from unittest import mock

import file_transfer
from file_transfer import (
    CHUNK_SIZE,
    DEFAULT_DOWNLOADS_DIR,
    compute_sha256,
    receive_file,
    send_file,
    send_file_async,
)
from protocol import receive_frame
from tcp_chat import ChatNode


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for expected state")


class FileTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src_dir = Path(self.tmp.name) / "src"
        self.downloads_dir = Path(self.tmp.name) / "downloads"
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        self.alice = ChatNode("Alice", host="127.0.0.1", peer_id="alice-id")
        self.bob = ChatNode("Bob", host="127.0.0.1", peer_id="bob-id")
        self.alice.start()
        self.bob.start()
        self.addCleanup(self.alice.stop)
        self.addCleanup(self.bob.stop)

        self.alice.connect("127.0.0.1", self.bob.port)
        wait_for(lambda: len(self.bob.get_peers()) == 1)

    def _register_collector(self, node, downloads_dir=None, **kwargs):
        received = []
        done = threading.Event()
        errors = []
        lock = threading.Lock()

        def handler(sock, header, address):
            try:
                saved = receive_file(
                    sock,
                    header,
                    address,
                    downloads_dir=downloads_dir if downloads_dir is not None else self.downloads_dir,
                    **kwargs,
                )
                with lock:
                    received.append((saved, header, address))
            except Exception as exc:
                with lock:
                    errors.append(exc)
                raise
            finally:
                done.set()

        node.register_file_handler(handler)
        return received, done, errors

    def test_zero_byte_file_transfer(self):
        received, done, errors = self._register_collector(self.bob)
        src = self.src_dir / "empty.txt"
        src.write_bytes(b"")

        progress = []
        result = send_file(self.alice, "bob-id", src, progress_cb=progress.append)

        self.assertTrue(done.wait(5.0))
        self.assertEqual(errors, [])
        self.assertEqual(result.size, 0)
        self.assertEqual(result.bytes_transferred, 0)
        self.assertEqual(progress, [100.0])

        saved_path, header, _ = received[0]
        self.assertEqual(header["type"], "FILE_OFFER")
        self.assertEqual(header["sender_id"], "alice-id")
        self.assertEqual(header["filename"], "empty.txt")
        self.assertEqual(header["size"], 0)
        self.assertTrue(saved_path.is_file())
        self.assertEqual(saved_path.read_bytes(), b"")
        self.assertEqual(compute_sha256(src), compute_sha256(saved_path))

    def test_normal_text_file_transfer(self):
        received, done, errors = self._register_collector(self.bob)
        src = self.src_dir / "notes.txt"
        content = ("Hello LAN chat!\nDòng tiếng Việt có dấu.\n" * 400).encode("utf-8")
        src.write_bytes(content)

        progress = []
        result = send_file(self.alice, "bob-id", src, progress_cb=progress.append)

        self.assertTrue(done.wait(5.0))
        self.assertEqual(errors, [])
        self.assertEqual(result.bytes_transferred, len(content))
        self.assertEqual(progress[-1], 100.0)

        saved_path, _, _ = received[0]
        self.assertEqual(saved_path.name, "notes.txt")
        self.assertEqual(saved_path.read_bytes(), content)
        self.assertEqual(compute_sha256(src), compute_sha256(saved_path))

    def test_utf8_filename_transfer(self):
        received, done, errors = self._register_collector(self.bob)
        utf8_name = "báo cáo dự án — tiếng Việt 日本語.txt"
        src = self.src_dir / utf8_name
        payload = "Nội dung UTF-8 đầy đủ ✅".encode("utf-8")
        src.write_bytes(payload)

        send_file(self.alice, "bob-id", src)

        self.assertTrue(done.wait(5.0))
        self.assertEqual(errors, [])
        saved_path, header, _ = received[0]
        self.assertEqual(header["filename"], utf8_name)
        self.assertEqual(saved_path.name, utf8_name)
        self.assertEqual(saved_path.read_bytes(), payload)
        self.assertEqual(compute_sha256(src), compute_sha256(saved_path))

    def test_binary_pdf_like_file_transfer(self):
        received, done, errors = self._register_collector(self.bob)
        src = self.src_dir / "slides.pdf"
        all_bytes = bytes(range(256))
        payload = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + (all_bytes * 1000) + b"\n%%EOF\n"
        src.write_bytes(payload)

        send_file(self.alice, "bob-id", src)

        self.assertTrue(done.wait(5.0))
        self.assertEqual(errors, [])
        saved_path, _, _ = received[0]
        self.assertEqual(saved_path.suffix, ".pdf")
        self.assertEqual(saved_path.read_bytes(), payload)
        self.assertEqual(compute_sha256(src), compute_sha256(saved_path))

    def test_large_file_at_least_10mb_transfer(self):
        received, done, errors = self._register_collector(self.bob)
        src = self.src_dir / "dataset_10mb.bin"
        # 10 MiB + 12,345 bytes (intentionally not aligned to 64 KiB chunk boundary).
        target_size = 10 * 1024 * 1024 + 12345
        pattern = hashlib.sha256(b"lan-chat-10mb-seed").digest() * 2048  # 64 KiB block
        written = 0
        with open(src, "wb") as handle:
            while written < target_size:
                block = pattern[: min(len(pattern), target_size - written)]
                handle.write(block)
                written += len(block)

        progress = []
        result = send_file(self.alice, "bob-id", src, progress_cb=progress.append)

        self.assertTrue(done.wait(15.0))
        self.assertEqual(errors, [])
        self.assertEqual(result.size, target_size)
        self.assertEqual(result.bytes_transferred, target_size)
        self.assertGreaterEqual(len(progress), 160)
        self.assertEqual(progress[0], 0.0)
        self.assertEqual(progress[-1], 100.0)
        self.assertTrue(all(0.0 <= p <= 100.0 for p in progress))
        self.assertTrue(all(a <= b for a, b in zip(progress, progress[1:])))
        self.assertTrue(all(p < 100.0 for p in progress[:-1]))

        saved_path, _, _ = received[0]
        self.assertEqual(saved_path.stat().st_size, target_size)
        self.assertEqual(compute_sha256(src), compute_sha256(saved_path))

    def test_progress_callback_monotonic_and_reaches_100(self):
        received, done, errors = self._register_collector(self.bob)
        src = self.src_dir / "progress_sample.bin"
        payload = os.urandom(CHUNK_SIZE * 4 + 1024)
        src.write_bytes(payload)

        sender_progress = []
        send_file(self.alice, "bob-id", src, progress_cb=sender_progress.append)

        self.assertTrue(done.wait(5.0))
        self.assertEqual(errors, [])
        # 5 chunks + initial 0.0 = 6 progress points.
        self.assertEqual(len(sender_progress), 6)
        self.assertEqual(sender_progress[0], 0.0)
        self.assertEqual(sender_progress[-1], 100.0)
        self.assertTrue(all(0.0 < p < 100.0 for p in sender_progress[1:-1]))
        self.assertTrue(all(a <= b for a, b in zip(sender_progress, sender_progress[1:])))
        self.assertEqual(received[0][0].read_bytes(), payload)

    def test_duplicate_filename_does_not_overwrite(self):
        received = []
        done_events = [threading.Event(), threading.Event(), threading.Event()]
        counter = {"idx": 0}

        def handler(sock, header, address):
            saved = receive_file(sock, header, address, downloads_dir=self.downloads_dir)
            received.append(saved)
            idx = counter["idx"]
            counter["idx"] += 1
            done_events[idx].set()

        self.bob.register_file_handler(handler)

        contents = [b"first version", b"second version", b"third version"]
        for i, body in enumerate(contents):
            src = self.src_dir / "report.pdf"
            src.write_bytes(body)
            send_file(self.alice, "bob-id", src)
            self.assertTrue(done_events[i].wait(5.0))

        names = [p.name for p in received]
        self.assertEqual(names, ["report.pdf", "report (1).pdf", "report (2).pdf"])
        for path, expected in zip(received, contents):
            self.assertEqual(path.read_bytes(), expected)

    def test_concurrent_duplicate_filenames_do_not_overwrite(self):
        barrier = threading.Barrier(2)
        saved_paths = []
        errors = []
        lock = threading.Lock()

        def run_receiver(payload):
            s_send, s_recv = socket.socketpair()
            try:
                s_send.settimeout(5.0)
                s_recv.settimeout(5.0)
                header = {"type": "FILE_OFFER", "filename": "concurrent.bin", "size": len(payload)}

                def writer():
                    barrier.wait(timeout=5.0)
                    s_send.sendall(payload)

                writer_thread = threading.Thread(target=writer)
                writer_thread.start()
                dest = receive_file(s_recv, header, ("127.0.0.1", 50000), downloads_dir=self.downloads_dir)
                writer_thread.join(timeout=5.0)
                with lock:
                    saved_paths.append(dest)
            except Exception as exc:
                with lock:
                    errors.append(exc)
            finally:
                s_send.close()
                s_recv.close()

        payload_a = b"A" * 8192
        payload_b = b"B" * 8192
        t1 = threading.Thread(target=run_receiver, args=(payload_a,))
        t2 = threading.Thread(target=run_receiver, args=(payload_b,))
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        self.assertEqual(errors, [])
        self.assertEqual(len(saved_paths), 2)
        self.assertEqual({p.name for p in saved_paths}, {"concurrent.bin", "concurrent (1).bin"})
        self.assertEqual({p.read_bytes() for p in saved_paths}, {payload_a, payload_b})

    def test_default_downloads_directory_storage(self):
        expected_dir = Path(file_transfer.__file__).resolve().parent / "downloads"
        self.assertEqual(DEFAULT_DOWNLOADS_DIR, expected_dir)

        unique_name = f"test_default_dl_{uuid.uuid4().hex}.txt"
        src = self.src_dir / unique_name
        payload = b"saved in project downloads directory"
        src.write_bytes(payload)

        received_paths = []
        done = threading.Event()

        def default_handler(sock, header, address):
            saved = receive_file(sock, header, address)
            received_paths.append(saved)
            done.set()

        self.bob.register_file_handler(default_handler)
        send_file(self.alice, "bob-id", src)

        self.assertTrue(done.wait(5.0))
        saved_path = received_paths[0]
        self.addCleanup(lambda: saved_path.unlink(missing_ok=True))

        self.assertEqual(saved_path.parent.resolve(), expected_dir.resolve())
        self.assertEqual(saved_path.name, unique_name)
        self.assertEqual(saved_path.read_bytes(), payload)

    def test_sender_uses_separate_tcp_connection(self):
        chat_conn_port = self.alice._connections["bob-id"].sock.getsockname()[1]
        observed = {}
        done = threading.Event()

        def inspect_handler(sock, header, address):
            observed["file_remote_port"] = address[1]
            observed["header"] = header
            observed["saved"] = receive_file(
                sock, header, address, downloads_dir=self.downloads_dir
            )
            done.set()

        self.bob.register_file_handler(inspect_handler)

        nested_dir = self.src_dir / "nested" / "sub"
        nested_dir.mkdir(parents=True, exist_ok=True)
        src = nested_dir / "separate.txt"
        src.write_bytes(b"dedicated tcp stream payload")

        real_open = self.alice.open_file_connection
        opened_sockets = []

        def tracked_open(peer_id):
            sock = real_open(peer_id)
            opened_sockets.append(sock)
            return sock

        with mock.patch.object(self.alice, "open_file_connection", side_effect=tracked_open) as spy:
            send_file(self.alice, "bob-id", src)
            spy.assert_called_once_with("bob-id")

        self.assertTrue(done.wait(5.0))
        self.assertEqual(len(opened_sockets), 1)
        # Dedicated socket must be closed after send_file returns.
        self.assertEqual(opened_sockets[0].fileno(), -1)
        # File transfer socket must not be the existing chat socket.
        self.assertNotEqual(observed["file_remote_port"], chat_conn_port)
        # Only basename is transmitted, never directory path.
        self.assertEqual(observed["header"]["filename"], "separate.txt")
        self.assertEqual(observed["saved"].read_bytes(), b"dedicated tcp stream payload")

        # Existing chat connection remains usable and uncorrupted.
        self.alice.send_message("bob-id", "Chat still works after file transfer")
        wait_for(lambda: len(self.bob.get_history("alice-id")) == 1)
        self.assertEqual(
            self.bob.get_history("alice-id")[0].text,
            "Chat still works after file transfer",
        )

    def test_receiver_reads_exact_advertised_payload_size_and_handles_fragmentation(self):
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)
        s_send.settimeout(5.0)
        s_recv.settimeout(5.0)

        payload = b"0123456789ABCDEF" * 10
        trailing = b"TRAILING_BYTES"
        header = {"type": "FILE_OFFER", "filename": "exact.bin", "size": len(payload)}

        def fragmented_writer():
            # Send in irregular small fragments to verify no single-recv assumption.
            idx = 0
            step = 1
            while idx < len(payload):
                s_send.sendall(payload[idx : idx + step])
                idx += step
                step = (step % 13) + 1
            s_send.sendall(trailing)

        writer = threading.Thread(target=fragmented_writer)
        writer.start()

        saved_path = receive_file(
            s_recv, header, ("127.0.0.1", 55555), downloads_dir=self.downloads_dir
        )
        writer.join(timeout=5.0)

        self.assertEqual(saved_path.read_bytes(), payload)
        # Socket still has exact trailing bytes unread, proving exact byte read.
        self.assertEqual(s_recv.recv(len(trailing)), trailing)

    def test_send_file_async_worker_thread_and_checksum(self):
        received, done, errors = self._register_collector(self.bob)
        src = self.src_dir / "async_payload.bin"
        src.write_bytes(os.urandom(200 * 1024))

        completed = []
        progress = []
        task = send_file_async(
            self.alice,
            "bob-id",
            src,
            progress_cb=progress.append,
            on_complete=completed.append,
        )

        self.assertNotEqual(task.thread, threading.current_thread())
        result = task.get_result(timeout=5.0)
        self.assertTrue(done.wait(5.0))
        self.assertEqual(errors, [])
        self.assertTrue(task.done)
        self.assertIsNone(task.error)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0], result)
        self.assertEqual(progress[-1], 100.0)
        self.assertEqual(compute_sha256(src), compute_sha256(received[0][0]))

    def test_send_file_first_frame_wire_format(self):
        """Verify raw wire format: FILE_OFFER JSON frame followed immediately by payload."""
        s_send, s_recv = socket.socketpair()
        self.addCleanup(s_send.close)
        self.addCleanup(s_recv.close)
        s_send.settimeout(5.0)
        s_recv.settimeout(5.0)

        src = self.src_dir / "wire_check.bin"
        payload = b"wire-format-verification-bytes" * 100
        src.write_bytes(payload)

        fake_node = mock.Mock()
        fake_node.peer_id = "sender-xyz"
        fake_node.open_file_connection.return_value = s_send

        captured = {}

        def reader():
            captured["header"] = receive_frame(s_recv)
            chunks = []
            while True:
                data = s_recv.recv(4096)
                if not data:
                    break
                chunks.append(data)
            captured["body"] = b"".join(chunks)

        reader_thread = threading.Thread(target=reader)
        reader_thread.start()

        send_file(fake_node, "peer-1", src)
        reader_thread.join(timeout=5.0)

        self.assertEqual(
            captured["header"],
            {
                "type": "FILE_OFFER",
                "sender_id": "sender-xyz",
                "filename": "wire_check.bin",
                "size": len(payload),
            },
        )
        self.assertEqual(captured["body"], payload)


if __name__ == "__main__":
    unittest.main()
