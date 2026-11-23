"""Wire protocol shared by all modules of LAN Chat & File Sharing.

One TCP frame: 4-byte unsigned big-endian header size + UTF-8 JSON header.
MESSAGE and FILE_OFFER headers are followed by exactly ``size`` raw bytes.
The file transfer uses a separate TCP connection from the chat connection.
UDP discovery uses independent datagrams and is owned by member 2.
"""
from __future__ import annotations

import json
import re
import socket
import struct
from typing import Any

MAX_HEADER_BYTES = 16 * 1024
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_FILE_BYTES = 2**40  # Hard safety bound; UI may enforce a smaller limit.
PROTOCOL_VERSION = 1


class ProtocolError(Exception):
    """Malformed or unsupported application-layer frame."""


class ConnectionClosed(ConnectionError):
    """Connection ended before the requested number of bytes arrived."""


def receive_exact(sock: socket.socket, count: int) -> bytes:
    """Read exactly count bytes, handling TCP fragmentation/coalescing."""
    if not isinstance(count, int) or not 0 <= count <= MAX_FILE_BYTES:
        raise ValueError("invalid byte count")
    result = bytearray()
    while len(result) < count:
        chunk = sock.recv(min(count - len(result), 64 * 1024))
        if not chunk:
            raise ConnectionClosed(f"expected {count} bytes, received {len(result)}")
        result.extend(chunk)
    return bytes(result)


def _encode_header(header: dict[str, Any]) -> bytes:
    if not isinstance(header, dict):
        raise ProtocolError("frame header must be an object")
    kind = header.get("type")
    if not isinstance(kind, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", kind):
        raise ProtocolError("invalid or missing frame type")
    try:
        body = json.dumps(header, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("frame is not valid JSON") from exc
    if len(body) > MAX_HEADER_BYTES:
        raise ProtocolError("frame header too large")
    return body


def send_frame(sock: socket.socket, header: dict[str, Any]) -> None:
    """Send one complete framed JSON header (no raw file bytes)."""
    body = _encode_header(header)
    sock.sendall(struct.pack("!I", len(body)) + body)


def receive_frame(sock: socket.socket) -> dict[str, Any]:
    """Return one JSON frame; leaves later frames or raw bytes in socket."""
    size = struct.unpack("!I", receive_exact(sock, 4))[0]
    if not 0 < size <= MAX_HEADER_BYTES:
        raise ProtocolError(f"header length {size} is invalid")
    raw = receive_exact(sock, size)
    try:
        header = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("invalid UTF-8 JSON header") from exc
    # Verify the type and size conventions, not an entire rigid schema:
    # member 3 can add file-only metadata without changing TCP Core.
    _encode_header(header)
    return header


def validate_message(text: str) -> None:
    if not isinstance(text, str) or not text:
        raise ValueError("message must be a non-empty string")
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("message exceeds maximum UTF-8 size")


def validate_file_offer(header: dict[str, Any]) -> None:
    """Validate the FILE_OFFER contract before passing to member 3."""
    if header.get("type") != "FILE_OFFER":
        raise ProtocolError("expected FILE_OFFER")
    name = header.get("filename")
    size = header.get("size")
    if not isinstance(name, str) or not name or len(name.encode("utf-8")) > 255:
        raise ProtocolError("invalid filename")
    if "/" in name or "\\" in name or name in (".", "..") or "\x00" in name:
        raise ProtocolError("filename must be a basename")
    if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
        raise ProtocolError("invalid file size")
