"""LAN presence announcements over IPv4 UDP, independent of TCP sessions."""
from dataclasses import dataclass
import json
import queue
import socket
import threading
import time


@dataclass(frozen=True)
class Peer:
    peer_id: str
    name: str
    host: str
    tcp_port: int
    status: str
    last_seen: float


class DiscoveryService:
    def __init__(self, peer_id, name, tcp_port, *, udp_port=9999,
                 broadcast="255.255.255.255"):
        self.peer_id = peer_id
        self.name = name
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.broadcast = broadcast
        self.events = queue.Queue()
        self._peers = {}
        self._status = "online"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._changed = threading.Event()
        self._socket = None
        self._threads = []

    def start(self):
        if self._socket is not None:
            raise RuntimeError("discovery already started")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass  # Some systems expose the constant without supporting it.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", self.udp_port))
            sock.settimeout(0.2)
        except OSError:
            sock.close()
            raise
        self._socket = sock
        self._stop.clear()
        self._changed.clear()
        for target in (self._listen, self._announce):
            worker = threading.Thread(target=target, args=(sock,), daemon=True)
            worker.start()
            self._threads.append(worker)

    def stop(self):
        self._stop.set()
        self._changed.set()
        for worker in self._threads:
            worker.join()
        self._threads.clear()
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        with self._lock:
            self._peers.clear()

    def get_peers(self):
        with self._lock:
            return sorted(self._peers.values(), key=lambda p: (p.name.casefold(), p.peer_id))

    def set_status(self, status):
        if status not in ("online", "away"):
            raise ValueError("status must be online or away")
        with self._lock:
            self._status = status
        self._changed.set()

    def _announce(self, sock):
        while not self._stop.is_set():
            self._changed.clear()
            with self._lock:
                status = self._status
            packet = dict(type="HELLO", peer_id=self.peer_id, name=self.name,
                          tcp_port=self.tcp_port, status=status)
            try:
                sock.sendto(json.dumps(packet).encode(), (self.broadcast, self.udp_port))
            except OSError as exc:
                self.events.put(f"UDP broadcast failed: {exc}")
            if not self._stop.is_set():
                self._changed.wait(3)

    def _listen(self, sock):
        while not self._stop.is_set():
            try:
                data, address = sock.recvfrom(4097)
            except socket.timeout:
                pass
            except OSError as exc:
                self.events.put(f"UDP receive failed: {exc}")
                self._stop.wait(0.2)
            else:
                self._observe(data, address[0], time.monotonic())
            self._expire(time.monotonic())

    def _observe(self, data, host, now):
        if len(data) > 4096:
            return
        try:
            packet = json.loads(data.decode("utf-8"))
            if not isinstance(packet, dict) or packet.get("type") != "HELLO":
                return
            pid, name = packet["peer_id"], packet["name"]
            port, status = packet["tcp_port"], packet["status"]
            if (not isinstance(pid, str) or not 1 <= len(pid) <= 128 or pid == self.peer_id
                    or not isinstance(name, str) or not 1 <= len(name.encode()) <= 128
                    or type(port) is not int or not 1 <= port <= 65535
                    or status not in ("online", "away")):
                return
        except (ValueError, KeyError, RecursionError):
            return
        peer = Peer(pid, name, host, port, status, now)
        with self._lock:
            previous = self._peers.get(pid)
            self._peers[pid] = peer
            if previous is None:
                self.events.put(f"{name} joined ({host}:{port}, {status})")
            elif previous.status != status:
                self.events.put(f"{name} is now {status}")

    def _expire(self, now):
        with self._lock:
            for pid, peer in list(self._peers.items()):
                if now - peer.last_seen >= 10:
                    del self._peers[pid]
                    self.events.put(f"{peer.name} went offline")
