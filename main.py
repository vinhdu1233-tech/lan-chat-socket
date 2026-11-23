"""LAN Chat launcher (leader-owned). Run: python main.py --name Alice --port 5001.

Until members add discovery.py and cli.py, this launches the minimal dev console.
The final /list/status/typing-safe UI belong to member 2, not this entry point.
"""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

from tcp_chat import ChatNode


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="LAN Chat & File Sharing peer")
    p.add_argument("--name", required=True, help="Display name of this peer")
    p.add_argument("--port", type=int, default=5001, help="Local TCP listening port")
    p.add_argument("--host", default="0.0.0.0", help="Local TCP bind interface")
    return p


def run_app(name: str, port: int, host: str = "0.0.0.0") -> None:
    """Wire up independent modules without modifying their implementations."""
    node = ChatNode(name=name, host=host, port=port)
    discovery: Any = None
    root = Path(__file__).resolve().parent
    try:
        node.start()
        print(f"[*] {node.name} peer_id={node.peer_id} | TCP {node.port}")
        if (root / "discovery.py").is_file():
            mod = importlib.import_module("discovery")
            # Member 2's documented interface. Fail visibly on incompatible API.
            discovery = mod.DiscoveryService(peer_id=node.peer_id, name=node.name,
                                             tcp_port=node.port)
            discovery.start()
        if (root / "file_transfer.py").is_file():
            transfer = importlib.import_module("file_transfer")
            # Member 3's receive_file handles FILE_OFFER on a separate TCP socket.
            node.register_file_handler(transfer.receive_file)
        ui_name = "cli" if (root / "cli.py").is_file() else "dev_console"
        ui = importlib.import_module(ui_name)
        ui.run_console(node, discovery)
    finally:
        if discovery is not None:
            discovery.stop()
        node.stop()


if __name__ == "__main__":
    args = make_parser().parse_args()
    try:
        run_app(args.name, args.port, args.host)
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Exiting")
