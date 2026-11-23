"""Reliable chunked TCP file transfer module (Member 3).

Protocol contract (see ``docs/INTEGRATION_CONTRACT.md``):
- File transfer ALWAYS uses a dedicated TCP socket separate from the chat
  socket so large payloads never block chat messages.
- First frame on the file socket is a framed JSON ``FILE_OFFER`` header:
  ``{"type": "FILE_OFFER", "sender_id": ..., "filename": ..., "size": ...}``
- Immediately followed by exactly ``size`` raw payload bytes streamed in
  64 KiB chunks using ``sendall()``.
- No extra completion ACK frame is added without Leader approval.

Threading responsibility:
- ``send_file()`` performs the transfer synchronously on the calling thread.
- The caller/UI (``cli.py``, owned by Member 2) is responsible for running
  outbound transfers in a background worker thread so user input and chat
  events remain responsive. ``send_file_async()`` is provided as a ready-to-use
  single-worker-thread helper that runs ``send_file()`` without spawning
  per-chunk threads or losing worker exceptions.
- Incoming transfers are already dispatched on their own worker thread by
  ``ChatNode._handle_incoming()``, which owns closing the accepted socket in
  its ``finally`` block after ``receive_file()`` returns.
"""
from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import socket
import stat
import tempfile
import threading
from typing import Any, Callable

from protocol import (
    ConnectionClosed,
    MAX_FILE_BYTES,
    ProtocolError,
    receive_exact,
    send_frame,
    validate_file_offer,
)
from tcp_chat import ChatEvent

CHUNK_SIZE = 64 * 1024  # 64 KiB chunk size required by integration contract.
TRANSFER_TIMEOUT = 30.0  # Per-socket inactivity timeout in seconds.
DEFAULT_DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"

ProgressCallback = Callable[[float], None]

_COMMIT_LOCK = threading.Lock()
_FORBIDDEN_FILENAME_CHARS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


@dataclass(frozen=True)
class TransferResult:
    """Metadata returned upon successful file transmission."""

    filename: str
    size: int
    bytes_transferred: int
    path: Path


class FileTransferTask:
    """Handle for an asynchronous file transfer running in a single worker thread."""

    def __init__(
        self,
        thread: threading.Thread,
        done_event: threading.Event,
        state: dict[str, Any],
    ) -> None:
        self.thread = thread
        self._done_event = done_event
        self._state = state

    @property
    def done(self) -> bool:
        return self._done_event.is_set()

    @property
    def result(self) -> TransferResult | None:
        return self._state.get("result")

    @property
    def error(self) -> Exception | None:
        return self._state.get("error")

    def join(self, timeout: float | None = None) -> bool:
        """Wait for the worker thread to finish; return True if finished."""
        finished = self._done_event.wait(timeout=timeout)
        if finished:
            self.thread.join(timeout=timeout)
        return finished

    def get_result(self, timeout: float | None = None) -> TransferResult:
        """Wait for completion and return TransferResult or re-raise worker error."""
        if not self.join(timeout=timeout):
            raise TimeoutError("file transfer worker did not complete in time")
        error = self._state.get("error")
        if error is not None:
            raise error
        result = self._state.get("result")
        if result is None:
            raise RuntimeError("file transfer worker finished without a result")
        return result


def _validate_positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _validate_timeout(timeout: float | None) -> float | None:
    if timeout is None:
        return None
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number or None")
    return float(timeout)


def sanitize_filename(filename: str) -> str:
    """Validate that ``filename`` is a safe cross-platform UTF-8 basename.

    Rejects path separators, directory traversal, drive prefixes, control
    characters, Windows-forbidden characters/device names, and names exceeding
    255 UTF-8 bytes. Raises ``ProtocolError`` on any violation.
    """
    if not isinstance(filename, str) or not filename or not filename.strip():
        raise ProtocolError("invalid or empty filename")
    if len(filename.encode("utf-8")) > 255:
        raise ProtocolError("filename exceeds 255 UTF-8 bytes")
    if "/" in filename or "\\" in filename or "\x00" in filename:
        raise ProtocolError("filename must be a basename without path separators")
    if filename in (".", ".."):
        raise ProtocolError("relative directory names are not allowed")
    if filename.endswith(".") or filename.endswith(" "):
        raise ProtocolError("filename cannot end with a dot or space")
    if any(ord(ch) < 32 or ord(ch) == 127 or ch in _FORBIDDEN_FILENAME_CHARS for ch in filename):
        raise ProtocolError("filename contains forbidden or control characters")
    if PurePosixPath(filename).name != filename or PureWindowsPath(filename).name != filename:
        raise ProtocolError("filename must be a plain basename")
    if PureWindowsPath(filename).drive:
        raise ProtocolError("filename must not include a drive specifier")
    stem = Path(filename).stem.upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        raise ProtocolError(f"filename uses reserved device name: {filename}")
    return filename


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate ``text`` cleanly on a UTF-8 character boundary to <= max_bytes."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


def _build_candidate_name(filename: str, index: int) -> str:
    """Return ``filename`` for index 0, or ``stem (index).ext`` for duplicates."""
    if index == 0:
        return filename
    parsed = Path(filename)
    suffix = parsed.suffix
    stem = parsed.stem
    tag = f" ({index})"
    candidate = f"{stem}{tag}{suffix}"
    if len(candidate.encode("utf-8")) <= 255:
        return candidate
    reserved = len(tag.encode("utf-8")) + len(suffix.encode("utf-8"))
    max_stem_bytes = max(1, 255 - reserved)
    trimmed_stem = _truncate_utf8(stem, max_stem_bytes) or "file"
    return f"{trimmed_stem}{tag}{suffix}"


def _safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _commit_temp_file(temp_path: Path, downloads_dir: Path, filename: str) -> Path:
    """Atomically move ``temp_path`` into ``downloads_dir`` without overwriting.

    Uses a process-wide lock plus ``os.link`` (which atomically fails with
    ``FileExistsError`` if the target exists on POSIX and NTFS) so concurrent
    transfers with identical filenames never overwrite each other. Falls back
    to ``O_CREAT | O_EXCL`` reservation + ``os.replace`` only on filesystems
    that do not support hard links.
    """
    resolved_dir = downloads_dir.resolve()
    with _COMMIT_LOCK:
        index = 0
        while True:
            candidate_name = _build_candidate_name(filename, index)
            destination = resolved_dir / candidate_name
            if destination.resolve(strict=False).parent != resolved_dir:
                raise ProtocolError("resolved destination escapes downloads directory")
            try:
                os.link(temp_path, destination)
            except FileExistsError:
                index += 1
                continue
            except OSError as exc:
                if exc.errno not in (
                    errno.EPERM,
                    errno.EOPNOTSUPP,
                    errno.EXDEV,
                    errno.ENOSYS,
                    errno.EINVAL,
                ):
                    raise
                # Fallback for filesystems without hard-link support (e.g., FAT32).
                try:
                    fd = os.open(
                        destination,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o644,
                    )
                except FileExistsError:
                    index += 1
                    continue
                os.close(fd)
                try:
                    os.replace(temp_path, destination)
                except Exception:
                    _safe_unlink(destination)
                    raise
                return destination
            else:
                _safe_unlink(temp_path)
                return destination


def _resolve_source_path(path: str | os.PathLike[str]) -> Path:
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError("source path must be a string or path-like object")
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ValueError("invalid source path")
    file_path = Path(raw)
    if not file_path.exists():
        raise FileNotFoundError(f"source file not found: {file_path}")
    if file_path.is_dir():
        raise IsADirectoryError(f"source path is a directory: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"source path is not a regular file: {file_path}")
    return file_path


def _open_dedicated_socket(
    node: Any, peer_id: Any, timeout: float | None
) -> socket.socket:
    if isinstance(peer_id, str):
        if not peer_id:
            raise ValueError("peer_id must be a non-empty string")
        return node.open_file_connection(peer_id)

    # Optional convenience: accept a discovered peer dict/object when no chat
    # connection has been opened yet, matching ChatNode.connect_to_peer().
    def _field(key: str) -> Any:
        return peer_id.get(key) if isinstance(peer_id, dict) else getattr(peer_id, key, None)

    host = _field("host") or _field("ip")
    port = _field("tcp_port")
    if host and port:
        connect_timeout = getattr(node, "connect_timeout", timeout or TRANSFER_TIMEOUT)
        return socket.create_connection((host, int(port)), timeout=connect_timeout)
    raise ValueError("peer_id must be a non-empty string or peer descriptor")


def _report_progress(progress_cb: ProgressCallback | None, percent: float) -> None:
    if progress_cb is not None:
        progress_cb(percent)


def compute_sha256(path: str | os.PathLike[str], chunk_size: int = CHUNK_SIZE) -> str:
    """Compute the SHA-256 hex digest of a file using chunked reads."""
    _validate_positive_int("chunk_size", chunk_size)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def send_file(
    node: Any,
    peer_id: str,
    path: str | os.PathLike[str],
    progress_cb: ProgressCallback | None = None,
    *,
    chunk_size: int = CHUNK_SIZE,
    timeout: float | None = TRANSFER_TIMEOUT,
) -> TransferResult:
    """Send a file to a peer through a dedicated TCP connection.

    Opens an independent TCP socket via ``node.open_file_connection(peer_id)``,
    transmits the ``FILE_OFFER`` JSON header frame using ``protocol.send_frame``,
    and streams the raw file payload in 64 KiB chunks via ``sock.sendall()``.

    Progress callback contract:
    - When provided, ``progress_cb(percent)`` is called with a ``float`` in
      the range ``0.0`` to ``100.0`` computed from actual transmitted payload
      bytes.
    - ``100.0`` is reported only after every advertised payload byte has been
      transmitted successfully (including for zero-byte files, without
      division-by-zero).

    Threading note:
    - This function executes synchronously. UI callers should run it on a
      dedicated worker thread (for example via ``send_file_async()``) so the
      chat console stays responsive.
    """
    _validate_positive_int("chunk_size", chunk_size)
    validated_timeout = _validate_timeout(timeout)
    source_path = _resolve_source_path(path)
    filename = sanitize_filename(source_path.name)

    with open(source_path, "rb") as file_obj:
        file_stat = os.fstat(file_obj.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(f"source path is not a regular file: {source_path}")
        total_size = file_stat.st_size
        if not 0 <= total_size <= MAX_FILE_BYTES:
            raise ValueError(f"file size out of allowed range: {total_size}")

        header = {
            "type": "FILE_OFFER",
            "sender_id": str(getattr(node, "peer_id", "")),
            "filename": filename,
            "size": total_size,
        }
        validate_file_offer(header)

        sock = _open_dedicated_socket(node, peer_id, validated_timeout)
        try:
            sock.settimeout(validated_timeout)
            send_frame(sock, header)

            if total_size == 0:
                _report_progress(progress_cb, 100.0)
                return TransferResult(
                    filename=filename,
                    size=0,
                    bytes_transferred=0,
                    path=source_path,
                )

            _report_progress(progress_cb, 0.0)
            bytes_sent = 0
            while bytes_sent < total_size:
                to_read = min(chunk_size, total_size - bytes_sent)
                chunk = file_obj.read(to_read)
                if not chunk:
                    raise OSError(
                        f"source file truncated while sending "
                        f"({bytes_sent}/{total_size} bytes read)"
                    )
                sock.sendall(chunk)
                bytes_sent += len(chunk)
                if bytes_sent < total_size:
                    percent = min(99.99, (bytes_sent / total_size) * 100.0)
                else:
                    percent = 100.0
                _report_progress(progress_cb, percent)

            return TransferResult(
                filename=filename,
                size=total_size,
                bytes_transferred=bytes_sent,
                path=source_path,
            )
        finally:
            try:
                sock.close()
            except OSError:
                pass


def send_file_async(
    node: Any,
    peer_id: str,
    path: str | os.PathLike[str],
    progress_cb: ProgressCallback | None = None,
    *,
    on_complete: Callable[[TransferResult], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    chunk_size: int = CHUNK_SIZE,
    timeout: float | None = TRANSFER_TIMEOUT,
) -> FileTransferTask:
    """Run ``send_file()`` in a single dedicated daemon worker thread.

    Designed for UI/CLI callers (e.g., ``cli.py``) so file transmission never
    blocks user input or chat event processing. Exceptions are stored on the
    returned ``FileTransferTask``, passed to ``on_error`` if provided, and
    emitted to ``node.events`` as a ``ChatEvent(kind="error", ...)`` when
    available so failures never silently disappear or crash the application.
    """
    done_event = threading.Event()
    state: dict[str, Any] = {"result": None, "error": None}

    def _worker() -> None:
        try:
            result = send_file(
                node,
                peer_id,
                path,
                progress_cb=progress_cb,
                chunk_size=chunk_size,
                timeout=timeout,
            )
            state["result"] = result
            if on_complete is not None:
                on_complete(result)
        except Exception as exc:
            state["error"] = exc
            if on_error is not None:
                on_error(exc)
            events_queue = getattr(node, "events", None)
            if events_queue is not None:
                pid = peer_id if isinstance(peer_id, str) else ""
                try:
                    events_queue.put(
                        ChatEvent(
                            kind="error",
                            peer_id=pid,
                            message=f"file transfer failed: {exc}",
                        )
                    )
                except Exception:
                    pass
        finally:
            done_event.set()

    thread = threading.Thread(
        target=_worker,
        name=f"file-send-{peer_id if isinstance(peer_id, str) else 'peer'}",
        daemon=True,
    )
    task = FileTransferTask(thread=thread, done_event=done_event, state=state)
    thread.start()
    return task


def receive_file(
    sock: socket.socket,
    header: dict[str, Any],
    address: tuple[str, int],
    *,
    downloads_dir: str | os.PathLike[str] | None = None,
    timeout: float | None = TRANSFER_TIMEOUT,
    chunk_size: int = CHUNK_SIZE,
    progress_cb: ProgressCallback | None = None,
) -> Path:
    """Receive a file from an already accepted TCP connection.

    The ``FILE_OFFER`` header has already been parsed by ``ChatNode``. This
    function validates the metadata, reads exactly ``header["size"]`` raw bytes
    into a temporary ``.part`` file inside ``downloads/``, and atomically
    publishes it to a unique non-overwriting destination only after all bytes
    are flushed and closed.

    On any error (invalid metadata, timeout, disconnect, truncated payload, or
    disk write failure), the temporary file is removed and the exception is
    propagated so ``ChatNode._handle_incoming()`` can report it safely without
    crashing the application.

    Socket ownership:
    - ``receive_file()`` applies ``timeout`` only to ``sock`` and does not
      close ``sock`` itself; ``ChatNode._handle_incoming()`` closes ``sock`` in
      its ``finally`` block.
    """
    del address  # Retained in signature to match ChatNode FileHandler contract.
    _validate_positive_int("chunk_size", chunk_size)
    validated_timeout = _validate_timeout(timeout)

    if not isinstance(header, dict):
        raise ProtocolError("FILE_OFFER header must be a dictionary")
    validate_file_offer(header)
    safe_name = sanitize_filename(header["filename"])
    expected_size: int = header["size"]

    target_dir = Path(downloads_dir) if downloads_dir is not None else DEFAULT_DOWNLOADS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    sock.settimeout(validated_timeout)

    temp_path: Path | None = None
    tmp_file = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target_dir,
            prefix=".tmp_",
            suffix=".part",
            delete=False,
        )
        temp_path = Path(tmp_file.name)

        if expected_size == 0:
            tmp_file.flush()
            tmp_file.close()
            tmp_file = None
            destination = _commit_temp_file(temp_path, target_dir, safe_name)
            temp_path = None
            _report_progress(progress_cb, 100.0)
            return destination

        _report_progress(progress_cb, 0.0)
        bytes_received = 0
        while bytes_received < expected_size:
            to_read = min(chunk_size, expected_size - bytes_received)
            chunk = receive_exact(sock, to_read)
            tmp_file.write(chunk)
            bytes_received += len(chunk)
            if bytes_received < expected_size:
                percent = min(99.99, (bytes_received / expected_size) * 100.0)
                _report_progress(progress_cb, percent)

        tmp_file.flush()
        tmp_file.close()
        tmp_file = None

        destination = _commit_temp_file(temp_path, target_dir, safe_name)
        temp_path = None
        _report_progress(progress_cb, 100.0)
        return destination
    except BaseException:
        if tmp_file is not None:
            try:
                tmp_file.close()
            except OSError:
                pass
        _safe_unlink(temp_path)
        raise
