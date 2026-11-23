# LAN Chat & File Sharing — Leader TCP Core

**Current state:** This package finishes the leader-owned foundation: `protocol.py`, `tcp_chat.py`, `main.py`. `dev_console.py` is a deliberately limited manual testing harness, **not** the finished rubric-compliant interface. UDP discovery/status, typing-safe CLI and actual file-transfer implementation are pending other members.

## Requirements

- Python **3.10+**, no extra libraries for the leader's TCP core.
- Run two terminals on one computer, or two computers on the same LAN.
- For communication between computers allow inbound TCP ports through the firewall.

## Quick demo on one machine

Terminal A:

```bash
python main.py --name Alice --port 5001
```

Terminal B:

```bash
python main.py --name Bob --port 5002
```

On A:

```text
/connect 127.0.0.1:5002
/list
/chat Bob
Hi Bob!
```

On B:

```text
/list
/chat Alice
Hi Alice!
```

B can initiate a connection to A instead. To test 3 peers, open a third terminal at `--port 5003` and connect from it to A. To test a real LAN, replace `127.0.0.1` with the listening computer's LAN IPv4 address.

### Known limitations of the manual harness

- `/list` shows **TCP-connected peers**, not UDP-discovered online peers.
- No discovery status, file sending or prompt redraw yet; member 2/3 will implement these.
- It may visually interrupt typed input on incoming events; member 2 must fix this in `cli.py`.
- No built-in persistence or end-to-end encryption is required by the assignment.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Architecture and integration contracts

Read [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md). It contains the event schema, file socket framing, API contracts expected from `discovery.py` and `cli.py`, and rules for `FILE_OFFER`. Modules must preserve the **same peer_id** across UDP announcements and TCP `HELLO`/`HELLO_ACK`.

## P2P principle

Every instance runs `ChatNode.start()` (local TCP acceptor) **and** can call `ChatNode.connect(...)` to other peers. No central chat server. A separate UDP discovery service finds peer addresses. File transfers use separate TCP sockets, keeping chat responsive.

## Submission checklist

Final submission additionally requires source code + README, 5–10 page report, Wireshark captures of UDP broadcast/TCP three-way handshake, and 10-minute live demo on at least 2 computers, per the assignment.
