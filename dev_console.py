"""Temporary manual smoke-test console. NOT the final typing-safe CLI (member 2).

Commands: /connect HOST:PORT, /list, /chat NAME|N|ID, /leave, /help, /quit.
Any other text goes to the active peer. This intentionally skips UDP / file transfer.
"""
from __future__ import annotations

import queue
import threading
from typing import Any

from tcp_chat import ChatNode


HELP = """Development-only commands:
  /connect 127.0.0.1:5002  manually connect via TCP (before UDP module exists)
  /list                    show currently TCP-connected peers ONLY
  /chat <name|number|id>   select peer, show prior history, clear unread
  /leave                   close the active chat TCP connection
  /help                    show this help
  /quit                    exit
  plain text              send to selected peer
The final /status, UDP /list, /send, typing-safe console are delegated to members.
"""


def _resolve(node: ChatNode, query: str) -> str:
    peers = node.get_peers()
    if query.isdigit() and 1 <= int(query) <= len(peers):
        return peers[int(query) - 1].peer_id
    matches = [p for p in peers if p.name == query or p.peer_id == query
               or p.peer_id.startswith(query)]
    if len(matches) != 1:
        raise ValueError("peer not found or name is ambiguous; use /list")
    return matches[0].peer_id


def _events(node: ChatNode, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            e = node.events.get(timeout=0.2)
        except queue.Empty:
            continue
        if e.kind == "message":
            print(f"\n[{e.peer_name}] {e.message}")
        elif e.kind == "unread":
            print(f"\n[*] New message from {e.peer_name} ({e.unread_count} unread)")
        elif e.kind == "connected":
            print(f"\n[*] Peer connected: {e.peer_name} ({e.peer_id[:8]})")
        elif e.kind == "disconnected":
            print(f"\n[*] Peer disconnected: {e.peer_name}")
        elif e.kind == "error":
            print(f"\n[!] {e.message}")
        # Writes are not prompt-safe; member 2 replaces this module.


def run_console(node: ChatNode, discovery: Any = None) -> None:
    del discovery
    stop = threading.Event()
    watcher = threading.Thread(target=_events, args=(node, stop), daemon=True)
    watcher.start()
    print(HELP)
    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            try:
                parts = line.split(maxsplit=1)
                command = parts[0]
                argument = parts[1] if len(parts) > 1 else ""
                if command == "/quit":
                    break
                if command == "/help":
                    print(HELP)
                elif command == "/connect":
                    if ":" not in argument:
                        print("Usage: /connect 127.0.0.1:5002")
                        continue
                    host, port = argument.rsplit(":", 1)
                    peer = node.connect(host, int(port))
                    print(f"[*] TCP connected to {peer.name} ({peer.peer_id[:8]})")
                elif command == "/list":
                    for idx, peer in enumerate(node.get_peers(), 1):
                        print(f"  {idx}. {peer.name} ({peer.host}:{peer.tcp_port}) "
                              f"{peer.peer_id[:8]} unread={peer.unread_count}")
                elif command == "/chat":
                    pid = _resolve(node, argument)
                    history = node.activate_chat(pid)
                    print(f"[*] Active chat: {node.get_peer(pid).name}")
                    for msg in history:
                        print(f"[{msg.sender}] {msg.text}")
                elif command == "/leave":
                    node.leave_chat()
                elif command.startswith("/"):
                    print("Unknown or unimplemented command in dev console. /help")
                else:
                    pid = node.active_peer_id
                    if pid is None:
                        print("[*] Select a peer with /chat first")
                    else:
                        node.send_message(pid, line)
                        print(f"[{node.name}] {line}")
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                print(f"[!] {exc}")
    finally:
        stop.set()
        watcher.join(timeout=1)
