# LAN Chat & File Sharing — Python Socket Project

Peer-to-peer chat/file-sharing assignment for a **three-person team**. Each peer runs one program; UDP discovers users and updates status, while TCP handles chat and file transfers.

> Current status: **Leader TCP Core implemented and tested (16/16 local unit tests)**. UDP discovery, production typing-safe CLI, actual file transfer, two-computer Wireshark evidence, and final report are **pending**.

## Run the current TCP-only demonstration
Requires Python 3.10+.

Terminal 1:
```bash
python3 main.py --name Alice --port 5001
```

Terminal 2:
```bash
python3 main.py --name Bob --port 5002
```

At Alice's prompt:
```text
/connect 127.0.0.1:5002
/list
/chat Bob
Hello Bob!
```

At Bob's prompt:
```text
/chat Alice
Hello Alice!
```

Add a third peer with `python3 main.py --name Charlie --port 5003` and connect it to Bob. Use the destination machine's LAN IPv4 instead of 127.0.0.1 when testing across computers.

**Important:** `dev_console.py` is a development-only console. Its `/list` shows TCP-connected peers, not UDP-discovered peers. Automatic discovery, `/status`, `/send`, and typing-safe input are not yet available.

## Tests
```bash
python3 -m unittest discover -s tests -v
```
Baseline: 16 tests passed locally on 2026-11-23. CI is defined in `.github/workflows/python-tests.yml` and runs on GitHub pushes/PRs.

## Documentation
- [Architecture and thread model](docs/ARCHITECTURE.md)
- [**Integration contract — REQUIRED before teammates code**](docs/INTEGRATION_CONTRACT.md)
- [Team assignments and acceptance criteria](docs/TEAM_TASKS.md)
- [Acceptance test plan](docs/TEST_PLAN.md)
- [Report + demo plan](docs/DEMO_AND_REPORT.md)
- [Project status](docs/PROJECT_STATUS.md)
- [GitHub collaboration guide](docs/GITHUB_SETUP.md)
- [Leader study notes (Vietnamese)](HUONG_DAN_LEADER.md)

## Work split
| Owner | Main files | Status |
|---|---|---|
| Leader | `protocol.py`, `tcp_chat.py`, `main.py`, TCP tests, integration | Core built; final integration pending |
| Member 2 | `discovery.py`, `cli.py`, UDP/CLI tests | Pending |
| Member 3 | `file_transfer.py`, file transfer/error tests | Pending |

## Submission requirements
Source + README, 5–10-page report, Wireshark screenshots demonstrating UDP broadcast and TCP three-way handshake, 10-minute live demo on at least **two physical computers**. These final deliverables remain pending.
