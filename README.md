# LAN Chat & File Sharing — Python Socket Project

Peer-to-peer chat and file-sharing application for a **three-person team**. Each peer runs a single program with **no central server** and **no external dependencies** (Python 3.10+ standard library only): UDP broadcasts discover online peers and status updates, while TCP handles bidirectional multi-peer chat and dedicated-socket file transfers.

> Current status: **All three core modules (TCP Core, UDP Discovery + Typing-safe CLI, and TCP File Transfer) are implemented and integrated (56/56 automated tests passing in CI across Ubuntu, macOS, and Windows)**. Physical two-computer LAN verification, Wireshark captures under `docs/evidence/`, the 5–10-page final report, and the 10-minute live demo remain **pending**.

## Requirements & Installation
- **Python 3.10+** (tested on Python 3.10 and 3.12 across Windows, macOS, and Linux).
- **No third-party packages required** — uses only the Python standard library.

```bash
git clone https://github.com/vinhdu1233-tech/lan-chat-socket.git
cd lan-chat-socket
```

## Running the Application
Start two (or more) peers in separate terminals (or on separate computers in the same LAN):

Terminal 1 (Alice):
```bash
python3 main.py --name Alice --port 5001
```
*(On Windows, use `py -3.12 main.py --name Alice --port 5001` if `python3` is not mapped.)*

Terminal 2 (Bob):
```bash
python3 main.py --name Bob --port 5002
```

Terminal 3 (optional — Charlie):
```bash
python3 main.py --name Charlie --port 5003
```

Within ~3 seconds, peers discover each other automatically over **UDP port 9999** (allow UDP `9999` and TCP `5001`–`5003` in the OS firewall when running across physical machines).

### Interactive Commands
| Command | Description |
|---|---|
| `/list` | Show UDP-discovered peers with stable index numbers, IP:port, and status (`online`/`away`) |
| `/chat <name\|number>` | Open a chat with a discovered peer (connects TCP automatically if needed), show history, and clear unread count |
| `<plain text>` | Send a UTF-8 chat message to the currently active peer |
| `/send <path>` | Send a file over a dedicated TCP connection in 64 KiB chunks with throttled progress updates (supports `"..."` and `'...'` quoted paths); received files are saved safely in `downloads/` |
| `/status online\|away` | Update your presence status and broadcast it immediately over UDP |
| `/leave` | Send `BYE` and close the active TCP chat connection |
| `/help` | Show available commands |
| `/quit` | Exit cleanly |

### Example Session
At Alice's prompt:
```text
/list
/chat 1
Hello Bob!
/send "path/to/slides.pdf"
```

At Bob's prompt:
```text
/chat Alice
Hello Alice!
/status away
```

Incoming messages, status changes, and `[File from ...]` receipt notifications are rendered without breaking a line currently being typed. `dev_console.py` remains in the repository only as a fallback development console if `cli.py` is absent.

## Automated Tests
```bash
python3 -m compileall -q .
python3 -m unittest discover -s tests -v
```

Test suite breakdown (**56 tests total**, 0 `ResourceWarning`s):
- `tests/test_protocol.py` (7 tests): 4-byte framing, TCP fragmentation/coalescing, header and `FILE_OFFER` validation.
- `tests/test_chat.py` (9 tests): bidirectional P2P chat, unread counters, history, leave/reconnect, simultaneous connection tie-break, file-handler dispatch.
- `tests/test_discovery.py` (6 tests): UDP presence refresh/10s expiry, duplicate names, status changes, malformed packet & version filtering, live UDP socket announce/receive/stop.
- `tests/test_cli.py` (6 tests): `/list` numbering, duplicate-name disambiguation, command errors, typing-safe redraw, throttled `/send` progress, `file_received` display.
- `tests/test_file_transfer.py` (13 tests): 0-byte, text, UTF-8 filenames, binary/PDF, >= 10 MB chunked streaming, monotonic 0–100% progress, sequential & concurrent duplicate-name protection, `downloads/` storage, dedicated TCP socket, exact payload reads, wire format, async worker.
- `tests/test_errors.py` (13 tests): invalid/missing paths, permission errors, invalid filenames, path traversal rejection, negative/invalid sizes, abrupt disconnect & partial `.part` cleanup, timeout, disk-full (`ENOSPC`) write failure, connection refused/reset, concurrent chat during active file transfer + SHA-256 verification.
- `tests/test_integration.py` (2 tests): full end-to-end tests combining real `DiscoveryService`, `ChatNode`, `file_transfer`, and `Console` with zero mocks.

GitHub Actions CI (`.github/workflows/python-tests.yml`) runs bytecode compilation and the full test suite on `ubuntu-latest`, `macos-latest`, and `windows-latest` for Python `3.10` and `3.12`.

## Documentation
- [Architecture and thread model](docs/ARCHITECTURE.md)
- [**Integration contract**](docs/INTEGRATION_CONTRACT.md)
- [Team assignments and acceptance criteria](docs/TEAM_TASKS.md)
- [Acceptance test plan](docs/TEST_PLAN.md)
- [Report + demo plan](docs/DEMO_AND_REPORT.md)
- [Project status](docs/PROJECT_STATUS.md)
- [GitHub collaboration guide](docs/GITHUB_SETUP.md)
- [Leader study notes (Vietnamese)](HUONG_DAN_LEADER.md)

## Work Split & Status
| Owner | Main files | Status |
|---|---|---|
| Leader | `protocol.py`, `tcp_chat.py`, `main.py`, TCP tests, integration | Implemented & merged on `main`; final 2-PC integration & report pending |
| Member 2 | `discovery.py`, `cli.py`, `tests/test_discovery.py`, `tests/test_cli.py` | Implemented & merged on `main` (PR #5) |
| Member 3 | `file_transfer.py`, `tests/test_file_transfer.py`, `tests/test_errors.py` | Implemented & merged on `main` (PR #4); integration polish on `fix/integration-improvements` |

## Remaining Submission Deliverables
- Physical two-computer LAN acceptance test log (`docs/TEST_PLAN.md` checklist)
- Annotated Wireshark screenshots (`docs/evidence/`) demonstrating UDP broadcast (`udp.port == 9999`), TCP 3-way handshake, and dedicated `FILE_OFFER` TCP stream
- Final 5–10-page project report
- 10-minute live demonstration on at least **two physical computers**
