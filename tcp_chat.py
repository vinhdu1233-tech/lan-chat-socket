"""Peer-to-peer TCP chat core; no central server and no terminal printing.

Each instance accepts incoming TCP connections and can connect to peers.
All asynchronous UI notifications enter ``events`` (Queue[ChatEvent]).
Member 2 owns UDP discovery + CLI; member 3 owns file transfer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import queue
import socket
import threading
import uuid
from typing import Any, Callable

from protocol import (ConnectionClosed, ProtocolError, PROTOCOL_VERSION,
                      MAX_MESSAGE_BYTES, receive_exact, receive_frame, send_frame,
                      validate_message, validate_file_offer)


@dataclass(frozen=True)
class ChatMessage:
    peer_id: str
    sender: str
    text: str
    outgoing: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ChatEvent:
    kind: str       # connected, disconnected, message, unread, error, chat_left
    peer_id: str = ""
    peer_name: str = ""
    message: str = ""
    unread_count: int = 0
    is_active: bool = False


@dataclass(frozen=True)
class PeerSummary:
    peer_id: str
    name: str
    host: str
    tcp_port: int
    unread_count: int


@dataclass
class _Connection:
    peer_id: str
    name: str
    host: str
    tcp_port: int
    sock: socket.socket
    direction: str  # incoming or outgoing
    write_lock: threading.Lock = field(default_factory=threading.Lock)


# The socket belongs to the file handler until it returns.
FileHandler = Callable[[socket.socket, dict[str, Any], tuple[str, int]], Any]


class ChatNode:
    def __init__(self, name: str, host: str = "0.0.0.0", port: int = 0,
                 peer_id: str | None = None, connect_timeout: float = 5.0):
        if not name or not isinstance(name, str) or len(name.encode("utf-8")) > 128:
            raise ValueError("name must be 1..128 UTF-8 bytes")
        if not 0 <= port <= 65535:
            raise ValueError("invalid TCP port")
        self.name = name
        self.peer_id = peer_id or uuid.uuid4().hex
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.events: queue.Queue[ChatEvent] = queue.Queue()
        self._running = threading.Event()
        self._lock = threading.RLock()
        self._server: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._connections: dict[str, _Connection] = {}
        self._history: dict[str, list[ChatMessage]] = {}
        self._unread: dict[str, int] = {}
        self._active_peer_id: str | None = None
        self._file_handler: FileHandler | None = None
        self._workers: set[threading.Thread] = set()

    @property
    def active_peer_id(self) -> str | None:
        with self._lock:
            return self._active_peer_id

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    def start(self) -> int:
        """Start listener; return actual TCP port (useful for --port 0 tests)."""
        if self._running.is_set():
            raise RuntimeError("already started")
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.host, self.port))
            server.listen(64)
            server.settimeout(0.25)
        except Exception:
            server.close()
            raise
        self._server = server
        self.port = server.getsockname()[1]
        self._running.set()
        self._accept_thread = threading.Thread(target=self._accept_loop,
                                               name=f"accept-{self.name}", daemon=True)
        self._accept_thread.start()
        return self.port

    def stop(self) -> None:
        self._running.clear()
        if self._server is not None:
            self._shutdown_socket(self._server)
            self._server = None
        with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()
            self._active_peer_id = None
        for conn in conns:
            self._shutdown_socket(conn.sock)
        if self._accept_thread and self._accept_thread is not threading.current_thread():
            self._accept_thread.join(timeout=2.0)
        with self._lock:
            workers = list(self._workers)
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=0.5)

    def __enter__(self) -> "ChatNode":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    @staticmethod
    def _shutdown_socket(sock: socket.socket) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _emit(self, kind: str, peer_id: str = "", peer_name: str = "",
              message: str = "", unread_count: int = 0, is_active: bool = False) -> None:
        self.events.put(ChatEvent(kind, peer_id, peer_name, message, unread_count, is_active))

    def _spawn(self, fn: Callable[..., None], *args: object) -> None:
        def run() -> None:
            try:
                fn(*args)
            finally:
                with self._lock:
                    self._workers.discard(threading.current_thread())
        t = threading.Thread(target=run, daemon=True)
        with self._lock:
            self._workers.add(t)
        t.start()

    def _accept_loop(self) -> None:
        while self._running.is_set():
            try:
                assert self._server is not None
                sock, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            sock.settimeout(self.connect_timeout)
            self._spawn(self._handle_incoming, sock, addr)

    def _handle_incoming(self, sock: socket.socket, addr: tuple[str, int]) -> None:
        handed_to_chat = False
        try:
            first = receive_frame(sock)
            kind = first["type"]
            if kind == "FILE_OFFER":
                validate_file_offer(first)
                handler = self._file_handler
                if handler is None:
                    send_frame(sock, {"type": "ERROR", "reason": "file handler unavailable"})
                    return
                sock.settimeout(None)
                saved = handler(sock, first, addr)
                sender_id = str(first.get("sender_id") or "")
                sender_name = ""
                if sender_id:
                    with self._lock:
                        peer_conn = self._connections.get(sender_id)
                        if peer_conn is not None:
                            sender_name = peer_conn.name
                display_sender = sender_name or sender_id or addr[0]
                filename = first["filename"]
                size = first["size"]
                detail = (
                    f"Received file '{filename}' ({size} bytes) -> {saved}"
                    if saved is not None
                    else f"Received file '{filename}' ({size} bytes)"
                )
                self._emit("file_received", sender_id, display_sender, detail)
                return
            if kind != "HELLO":
                raise ProtocolError("first chat frame must be HELLO")
            peer_id, peer_name, peer_port = self._identity(first)
            if peer_id == self.peer_id:
                raise ProtocolError("self-connection rejected")
            send_frame(sock, {"type": "HELLO_ACK", "version": PROTOCOL_VERSION,
                              "peer_id": self.peer_id, "name": self.name,
                              "tcp_port": self.port})
            sock.settimeout(None)
            conn = _Connection(peer_id, peer_name, addr[0], peer_port, sock, "incoming")
            if self._register(conn):
                handed_to_chat = True
                self._receive_loop(conn)
        except (ConnectionClosed, ProtocolError, OSError, ValueError) as exc:
            if self._running.is_set():
                self._emit("error", message=f"incoming connection {addr[0]}: {exc}")
        except Exception as exc:
            self._emit("error", message=f"incoming worker error: {exc}")
        finally:
            if not handed_to_chat:
                self._shutdown_socket(sock)

    @staticmethod
    def _identity(header: dict[str, Any]) -> tuple[str, str, int]:
        if header.get("version") != PROTOCOL_VERSION:
            raise ProtocolError("incompatible protocol version")
        pid = header.get("peer_id")
        name = header.get("name")
        port = header.get("tcp_port")
        if not isinstance(pid, str) or not 1 <= len(pid) <= 128:
            raise ProtocolError("invalid peer_id")
        if not isinstance(name, str) or not 1 <= len(name.encode("utf-8")) <= 128:
            raise ProtocolError("invalid name")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ProtocolError("invalid tcp_port")
        return pid, name, port

    def connect(self, host: str, port: int, expected_peer_id: str | None = None) -> PeerSummary:
        """Connect to a peer; expected_peer_id may come from UDP discovery."""
        if not self._running.is_set():
            raise RuntimeError("start() must be called first")
        sock = socket.create_connection((host, port), timeout=self.connect_timeout)
        try:
            send_frame(sock, {"type": "HELLO", "version": PROTOCOL_VERSION,
                              "peer_id": self.peer_id, "name": self.name,
                              "tcp_port": self.port})
            ack = receive_frame(sock)
            if ack["type"] != "HELLO_ACK":
                raise ProtocolError("peer did not acknowledge chat handshake")
            peer_id, name, reported_port = self._identity(ack)
            if peer_id == self.peer_id:
                raise ProtocolError("cannot connect to self")
            if expected_peer_id and peer_id != expected_peer_id:
                raise ProtocolError("peer ID does not match UDP discovery")
            sock.settimeout(None)
            conn = _Connection(peer_id, name, host, reported_port, sock, "outgoing")
            if self._register(conn):
                self._spawn(self._receive_loop, conn)
            else:
                self._shutdown_socket(sock)
            return self.get_peer(peer_id)
        except Exception:
            self._shutdown_socket(sock)
            raise

    def connect_to_peer(self, peer: Any) -> PeerSummary:
        """Adapter for member 2: object/dict with peer_id, host/IP, tcp_port."""
        def value(key: str, default: Any = None) -> Any:
            return peer.get(key, default) if isinstance(peer, dict) else getattr(peer, key, default)
        host = value("host") or value("ip")
        port = value("tcp_port")
        if not host or not port:
            raise ValueError("peer must provide host/ip and tcp_port")
        return self.connect(host, int(port), expected_peer_id=value("peer_id"))

    def _register(self, conn: _Connection) -> bool:
        """One socket per peer; deterministic tie-break for simultaneous connections."""
        replaced: _Connection | None = None
        with self._lock:
            old = self._connections.get(conn.peer_id)
            if old:
                preferred = "outgoing" if self.peer_id < conn.peer_id else "incoming"
                # Favor the connection initiated by the lexicographically smaller ID.
                if old.direction == preferred or conn.direction != preferred:
                    return False
                replaced = old
            self._connections[conn.peer_id] = conn
            self._history.setdefault(conn.peer_id, [])
            self._unread.setdefault(conn.peer_id, 0)
        if replaced:
            self._shutdown_socket(replaced.sock)
        self._emit("connected", conn.peer_id, conn.name)
        return True

    def _receive_loop(self, conn: _Connection) -> None:
        try:
            while self._running.is_set():
                header = receive_frame(conn.sock)
                kind = header["type"]
                if kind == "MESSAGE":
                    size = header.get("size")
                    if type(size) is not int or not 1 <= size <= MAX_MESSAGE_BYTES:
                        raise ProtocolError("invalid message byte length")
                    try:
                        text = receive_exact(conn.sock, size).decode("utf-8")
                        validate_message(text)
                    except (UnicodeDecodeError, ValueError) as exc:
                        raise ProtocolError("invalid UTF-8 message") from exc
                    with self._lock:
                        active = (self._active_peer_id == conn.peer_id)
                        self._history.setdefault(conn.peer_id, []).append(
                            ChatMessage(conn.peer_id, conn.name, text, False))
                        if not active:
                            self._unread[conn.peer_id] = self._unread.get(conn.peer_id, 0) + 1
                        unread = self._unread.get(conn.peer_id, 0)
                    self._emit("message" if active else "unread", conn.peer_id,
                               conn.name, text, unread, active)
                elif kind == "BYE":
                    break
                else:
                    raise ProtocolError(f"unexpected chat frame: {kind}")
        except (ConnectionClosed, ConnectionError, OSError):
            pass
        except (ProtocolError, ValueError) as exc:
            self._emit("error", conn.peer_id, conn.name, str(exc))
        finally:
            self._drop(conn)
            self._shutdown_socket(conn.sock)

    def _drop(self, conn: _Connection) -> None:
        with self._lock:
            if self._connections.get(conn.peer_id) is not conn:
                return  # A newer socket replaced this one.
            del self._connections[conn.peer_id]
            if self._active_peer_id == conn.peer_id:
                self._active_peer_id = None
        self._emit("disconnected", conn.peer_id, conn.name)

    def get_peers(self) -> list[PeerSummary]:
        """Currently connected TCP peers; not the UDP online-peers list."""
        with self._lock:
            return [PeerSummary(p.peer_id, p.name, p.host, p.tcp_port,
                                self._unread.get(p.peer_id, 0))
                    for p in self._connections.values()]

    def get_peer(self, peer_id: str) -> PeerSummary:
        with self._lock:
            conn = self._connections.get(peer_id)
            if conn is None:
                raise KeyError(f"peer {peer_id} not connected")
            return PeerSummary(conn.peer_id, conn.name, conn.host, conn.tcp_port,
                               self._unread.get(peer_id, 0))

    def activate_chat(self, peer_id: str) -> list[ChatMessage]:
        """Choose current chat and mark its messages read; return history copy."""
        with self._lock:
            if peer_id not in self._connections:
                raise KeyError(f"peer {peer_id} not connected")
            self._active_peer_id = peer_id
            self._unread[peer_id] = 0
            return list(self._history.get(peer_id, []))

    def deactivate_chat(self) -> None:
        """Leave chat selection WITHOUT closing the TCP connection."""
        with self._lock:
            self._active_peer_id = None

    def get_history(self, peer_id: str) -> list[ChatMessage]:
        with self._lock:
            return list(self._history.get(peer_id, []))

    def unread_count(self, peer_id: str) -> int:
        with self._lock:
            return self._unread.get(peer_id, 0)

    def send_message(self, peer_id: str, text: str) -> None:
        validate_message(text)
        with self._lock:
            conn = self._connections.get(peer_id)
        if conn is None:
            raise KeyError(f"peer {peer_id} not connected")
        data = text.encode("utf-8")
        try:
            with conn.write_lock:
                send_frame(conn.sock, {"type": "MESSAGE", "size": len(data)})
                conn.sock.sendall(data)
        except OSError:
            self._drop(conn)
            self._shutdown_socket(conn.sock)
            raise
        with self._lock:
            self._history.setdefault(peer_id, []).append(
                ChatMessage(peer_id, self.name, text, True))

    def leave_chat(self, peer_id: str | None = None) -> None:
        """Send BYE and close TCP chat connection, as specified by /leave."""
        with self._lock:
            target = peer_id or self._active_peer_id
            conn = self._connections.get(target) if target else None
        if conn is None:
            raise KeyError("no active connection to leave")
        try:
            with conn.write_lock:
                send_frame(conn.sock, {"type": "BYE"})
        except OSError:
            pass
        finally:
            self._drop(conn)
            self._shutdown_socket(conn.sock)

    def register_file_handler(self, handler: FileHandler) -> None:
        """Member 3 calls this; handler receives initial FILE_OFFER frame."""
        self._file_handler = handler

    def open_file_connection(self, peer_id: str) -> socket.socket:
        """Member 3 uses this to open an independent TCP socket for file data.

        Caller must send FILE_OFFER and raw bytes, and close the returned socket.
        """
        peer = self.get_peer(peer_id)
        return socket.create_connection((peer.host, peer.tcp_port),
                                        timeout=self.connect_timeout)
