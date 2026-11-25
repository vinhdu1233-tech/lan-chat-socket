"""Interactive LAN chat console. Uses only the standard library."""
from contextlib import contextmanager
import os
import queue
import shutil
import sys
import threading
import unicodedata

from protocol import ProtocolError


HELP = ("/list | /chat <name|number> | /send <path> | /leave | "
        "/status <online|away> | /help | /quit. Type text to chat.")


@contextmanager
def keyboard():
    """Read single keys without echo, restoring terminal settings on exit."""
    if os.name == "nt":
        import msvcrt

        def get_key():
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()  # Function and arrow keys have a second code.
                return ""
            if 0xD800 <= ord(key) <= 0xDBFF:
                pair = key + msvcrt.getwch()
                return pair.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
            return key

        yield get_key
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            def get_key():
                key = sys.stdin.read(1)
                if not key:
                    raise EOFError
                return key
            yield get_key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


class Terminal:
    def __init__(self, stream, interactive):
        self.stream = stream
        self.interactive = interactive
        self.lock = threading.Lock()
        self.buffer = ""
        self.editing = False

    def _clear(self):
        columns = shutil.get_terminal_size().columns
        self.stream.write("\r" + " " * max(0, columns - 1) + "\r")

    def _draw(self):
        # Keep long input on one row, including double-width CJK characters.
        room = max(0, shutil.get_terminal_size().columns - 3)
        visible = []
        for char in reversed(self.buffer):
            room -= 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            if room < 0:
                break
            visible.append(char)
        self.stream.write("> " + "".join(reversed(visible)))

    def notice(self, text):
        # Render remote text as text, including any terminal control characters.
        safe = "".join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))
        with self.lock:
            if self.editing:
                self._clear()
            self.stream.write(safe + "\n")
            if self.editing:
                self._draw()
            self.stream.flush()

    def read_line(self, get_key):
        if not self.interactive:
            return input("> ")
        with self.lock:
            self.editing = True
            self.buffer = ""
            self._draw()
            self.stream.flush()
        escape = ""
        try:
            while True:
                key = get_key()
                if key in ("\r", "\n"):
                    return self.buffer
                if key in ("\x03", "\x04", "\x1a"):
                    raise EOFError
                if key == "\x1b":
                    escape = "start"
                    continue
                if escape == "start":
                    escape = "sequence" if key in ("[", "O") else ""
                    continue
                if escape == "sequence":
                    if "@" <= key <= "~":
                        escape = ""
                    continue
                with self.lock:
                    if key in ("\x08", "\x7f"):
                        self.buffer = self.buffer[:-1]
                    elif key and key.isprintable():
                        self.buffer += key
                    else:
                        continue
                    self._clear()
                    self._draw()
                    self.stream.flush()
        finally:
            with self.lock:
                self.editing = False
                self.stream.write("\n")
                self.stream.flush()


class Console:
    def __init__(self, node, discovery, notice):
        self.node = node
        self.discovery = discovery
        self.notice = notice
        self.listed = []

    def _chat(self, target):
        peers = self.discovery.get_peers()
        if target.isascii() and target.isdecimal():
            index = int(target) - 1
            if not 0 <= index < len(self.listed):
                raise ValueError("Choose a number from /list")
            peers = [p for p in peers if p.peer_id == self.listed[index]]
        else:
            peers = [p for p in peers if p.name.casefold() == target.casefold()]
        if not peers:
            raise ValueError("Peer unavailable. Check /list")
        if len(peers) > 1:
            raise ValueError("Several peers have that name. Use /list then /chat <number>")
        peer = peers[0]
        if all(p.peer_id != peer.peer_id for p in self.node.get_peers()):
            self.node.connect_to_peer(peer)
        history = self.node.activate_chat(peer.peer_id)
        self.notice(f"Chatting with {peer.name} ({peer.host}:{peer.tcp_port})")
        for msg in history:
            self.notice(f"[{msg.sender}] {msg.text}")

    def _send_file(self, peer_id, path):
        try:
            from file_transfer import send_file
        except ImportError as exc:
            self.notice(f"File transfer unavailable: {exc}")
            return
        try:
            send_file(self.node, peer_id, path,
                      progress_cb=lambda percent: self.notice(f"Sending {path}: {percent}%"))
        except Exception as exc:
            self.notice(f"File transfer failed: {exc}")

    def handle(self, line):
        """Return False only when the user requests a clean exit."""
        try:
            if not line.strip():
                return True
            if not line.startswith("/"):
                peer_id = self.node.active_peer_id
                if not peer_id:
                    raise ValueError("Open a chat first with /chat <name|number>")
                self.node.send_message(peer_id, line)
                return True
            parts = line.split(maxsplit=1)
            cmd, arg = parts[0], parts[1].strip() if len(parts) == 2 else ""
            if cmd == "/list" and not arg:
                peers = self.discovery.get_peers()
                self.listed = [p.peer_id for p in peers]
                if not peers:
                    self.notice("No peers discovered")
                for index, p in enumerate(peers, 1):
                    self.notice(f"{index}. {p.name} ({p.host}:{p.tcp_port}) {p.status}")
            elif cmd == "/chat" and arg:
                self._chat(arg)
            elif cmd == "/send" and arg:
                peer_id = self.node.active_peer_id
                if not peer_id:
                    raise ValueError("Open a chat before sending a file")
                path = arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] == '"' else arg
                threading.Thread(target=self._send_file, args=(peer_id, path), daemon=True).start()
            elif cmd == "/status" and arg in ("online", "away"):
                self.discovery.set_status(arg)
                self.notice(f"Your status: {arg}")
            elif cmd == "/leave" and not arg:
                self.node.leave_chat()
            elif cmd == "/quit" and not arg:
                return False
            elif cmd == "/help" and not arg:
                self.notice(HELP)
            else:
                self.notice(f"Invalid command. {HELP}")
        except (KeyError, OSError, ValueError, RuntimeError, ProtocolError) as exc:
            self.notice(f"Error: {exc}")
        return True

    def show_chat_event(self, event):
        if event.kind == "message":
            self.notice(f"[{event.peer_name}] {event.message}")
        elif event.kind == "unread":
            if self.node.unread_count(event.peer_id):
                self.notice(f"New message from {event.peer_name} ({event.unread_count} unread)")
        elif event.kind == "error":
            self.notice(f"Error: {event.message}")
        else:
            self.notice(f"{event.peer_name} {event.kind}")

    def show_events(self, stop):
        while not stop.is_set():
            for source, show in ((self.node.events, self.show_chat_event),
                                 (self.discovery.events, self.notice)):
                for _ in range(64):
                    try:
                        event = source.get_nowait()
                    except queue.Empty:
                        break
                    show(event)
            stop.wait(0.04)


def run_console(node, discovery):
    terminal = Terminal(sys.stdout, sys.stdin.isatty() and sys.stdout.isatty())
    console = Console(node, discovery, terminal.notice)
    terminal.notice(HELP)
    stop = threading.Event()
    worker = threading.Thread(target=console.show_events, args=(stop,), daemon=True)
    worker.start()
    try:
        if terminal.interactive:
            with keyboard() as get_key:
                while console.handle(terminal.read_line(get_key)):
                    pass
        else:
            while console.handle(terminal.read_line(None)):
                pass
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        stop.set()
        worker.join()
