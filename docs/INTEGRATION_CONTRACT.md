# Integration contract — implemented interfaces

Original team interface agreement, updated after PR #6.

## 1. Architecture

Each peer runs an **independent TCP server** and may initiate TCP connections to other peers. **No central chat server.** UDP discovery belongs to member 2. Chat text and files use TCP, but file transfers have their own socket so they never block the chat stream.

## 2. Protocol (LEADER; implemented)

Every TCP connection begins with one **header frame**:

1. **4 bytes** unsigned big-endian number `header_len`.
2. Exactly `header_len` bytes: a UTF-8 JSON dictionary with uppercase `type`.
3. For message / file types, exactly `size` raw bytes **immediately following that header**.

`send_frame(sock, header)` and `receive_frame(sock)` process only the JSON header. `receive_exact(sock, size)` is required for payload. No message boundaries may be inferred from a single `recv()`.

### Chat handshake

Initiator sends:

```json
{"type":"HELLO","version":1,"peer_id":"abc123","name":"Alice","tcp_port":5001}
```

Receiver responds:

```json
{"type":"HELLO_ACK","version":1,"peer_id":"def456","name":"Bob","tcp_port":5002}
```

The `peer_id` must be reused for UDP discovery and TCP; it is stable for a program session. Each `ChatNode` creates a UUID unless explicitly provided.

### Chat

- Header: `{"type":"MESSAGE","size":18}`; followed by **18 raw bytes** of UTF-8 chat text (example size only).
- To end a chat connection: `{"type":"BYE"}`.
- TCP max message size **1 MiB UTF-8**; headers max **16 KiB**.
- Because TCP messages and file content use separate sockets, `FILE_OFFER` is never sent on an existing chat socket.

### File transfer (Member 3 — implemented)

Open a **new TCP socket** to the recipient's TCP listener. Send:

```json
{"type":"FILE_OFFER","sender_id":"abc123","filename":"slides.pdf","size":123456}
```

Then transmit **exactly 123456 file bytes**, in chunks, using `sock.sendall` and display progress based on file bytes sent. Receiver is called with this header already parsed by leader's TCP listener; it reads exactly `size` bytes, validates/sanitizes the filename, writes to `downloads/`, detects interruption and removes partial files. The file handler owns this socket until it returns (leader closes it in `finally`). No final application-level file completion ACK is currently implemented. If no file handler is installed, the receiver responds with `{ "type": "ERROR", "reason": "file handler unavailable" }` and closes the connection.

**Important:** `open_file_connection(peer_id)` works for existing TCP-connected peers. Member 3 can also connect to a discovered peer's `host:tcp_port` if the chat connection is not yet open; do not require a chat socket just to transfer a file unless the UI says so. Sender must close the file socket. Do not transmit directory paths as filenames; only use the basename. Consider duplicate file names and failed/cancelled transfers. No resuming required by the assignment.

## 3. Leader's API — `ChatNode` (already implemented)

```python
node = ChatNode(name="Alice", host="0.0.0.0", port=5001)
node.start()                # starts receiving TCP immediately
node.peer_id                # share with discovery
node.port                   # actual TCP port
node.connect(host, port, expected_peer_id=None)
node.connect_to_peer(peer)  # peer is dict or object with peer_id, host/ip, tcp_port
node.get_peers()            # connected peers, PeerSummary objects
node.get_peer(peer_id)
node.activate_chat(peer_id) # returns prior history; resets unread
node.deactivate_chat()      # deselect only, keep socket
node.send_message(peer_id, text)
node.leave_chat(peer_id=None) # sends BYE, closes chat socket
node.unread_count(peer_id)
node.get_history(peer_id)
node.open_file_connection(peer_id)
node.register_file_handler(handler)
node.stop()
```

`ChatNode.events` is a thread-safe `queue.Queue[ChatEvent]`. Each event has fields `kind`, `peer_id`, `peer_name`, `message`, `unread_count`, `is_active`. Event kinds:

- `connected`: TCP session established.
- `message`: message arrived from current/active peer; UI should print it immediately.
- `unread`: message arrived from another peer; show count, preserve history.
- `disconnected`: connection closed/peer crashed.
- `error`: recoverable error; `message` contains explanatory text.
- `file_received`: completed download notification emitted after the receive handler returns successfully.

UI must **not** read TCP sockets directly; it consumes these events. Chat histories and unread counters are guarded by locks inside the TCP core. This is in-memory message history, not durable database storage.

## 4. Member 2 — required modules

`discovery.py` provides:

```python
service = DiscoveryService(peer_id=node.peer_id, name=node.name,
                           tcp_port=node.port)
service.start()
service.get_peers()  # list of dict/objects with peer_id, name, host/ip, tcp_port, status
service.set_status("online")
service.stop()
```

Required behavior: broadcast every 3 seconds on UDP 9999, listen on the same fixed UDP port, expire peers after 10 seconds, report online/offline events and support statuses `online`/`away`. `SO_REUSEADDR`/`SO_REUSEPORT` before bind helps when testing 3 peers on one host. Use `peer_id` to ignore own announcements. UDP messages use JSON with `type: HELLO`, `version: 1`, `peer_id`, `name`, `tcp_port`, and `status`. The receiver checks an included version against 1.

`cli.py` provides:

```python
def run_console(node: ChatNode, discovery: DiscoveryService) -> None:
    ...
```

`/list` must use **discovery.get_peers()**, not merely TCP-connected peers. `/chat <name|number>` resolves the discovered peer and calls `node.connect_to_peer(peer)` only if not already connected; then `node.activate_chat(peer_id)`. `/leave` calls `node.leave_chat()`. `/send <path>` delegates to member 3's file module. `/status online|away` delegates to discovery. Ordinary input invokes `node.send_message(node.active_peer_id, text)`. `/help`, `/quit`, invalid commands need handling. Events arriving during typing **must not erase input**: use `prompt_toolkit` with `patch_stdout()` or a manual cursor-buffer renderer protected by an output lock. UI and UDP status are not part of the leader's implementation.

Member 2 should expose its own queue/event callback for UDP online/offline notifications. No changes to `tcp_chat.py` are required.

## 5. Member 3 — required module

`file_transfer.py` should implement a clear sender function and receiver callback. Suggested contract:

```python
def send_file(node: ChatNode, peer_id: str, path: str, progress_cb=None):
    ...

def receive_file(sock, header: dict, address: tuple[str,int]):
    ...

# main.py automatically registers receive_file when file_transfer.py is present.
# For independent tests, a fixture can also call node.register_file_handler(receive_file).
```

The sender opens a separate TCP socket through `node.open_file_connection(peer_id)`, sends `FILE_OFFER`, streams raw data in 64 KiB chunks and tracks percent. Receiver validates file name and size (leader pre-validates this), writes to `downloads/` safely, sets a reasonable inactivity timeout, and cleans up partials on error. Chat must function during active file transfer. Introduce a **separate worker thread** to run `send_file` from the UI, rather than blocking input.

Any change to wire protocol needs leader review **before** coding. Unit tests: empty file, non-ASCII filename, binary PDF, 10MB payload, missing file, disconnect mid-transfer, duplicate filename, chat during transfer, and checksum match.

## 6. Startup wiring

`main.py` starts leader's `ChatNode`, then (if available) starts `DiscoveryService`, registers the `file_transfer.receive_file` callback when member 3's module is present, then imports `cli.run_console(node, discovery)`. Before those files exist, `dev_console.py` serves as a temporary manual test. **No one should replace `main.py`;** add the specified modules and it will switch automatically.

## 7. Testing and scope

`python -m unittest discover -s tests -v` runs the integrated 56-test suite, including two end-to-end integration tests. Demo on at least **two computers**; use three local terminals for development. Final submission also needs README, report 5–10 pages and Wireshark captures.

## 8. Separation of ownership

- **Leader:** `protocol.py`, `tcp_chat.py`, `main.py`, `tests/test_protocol.py`, `tests/test_chat.py`; architecture, PR reviews and integration.
- **Member 2:** `discovery.py`, `cli.py`, UDP tests, console redraw tests.
- **Member 3:** `file_transfer.py`, transfer tests, Wireshark evidence and reliability cases.

If an integration problem requires changing an owned file, first create an issue or comment in a PR instead of both members editing the same file.
