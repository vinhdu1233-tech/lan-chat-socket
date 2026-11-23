# Project status — 2026-11-23

## Published to GitHub
- Leader's `protocol.py`, `tcp_chat.py`, `main.py`, temporary `dev_console.py`.
- TCP unit tests (16 local passes) and GitHub Actions workflow.
- Integration contract, architecture and team task documents.
- GitHub repository: https://github.com/vinhdu1233-tech/lan-chat-socket

## Done locally
- P2P TCP listener and client, HELLO/HELLO_ACK.
- Message framing and exact TCP read; multiple peers, unread and in-memory history.
- Threaded receivers, duplicate connection arbitration, disconnect/reconnect.
- Separate file socket routing interface (not actual file sender/receiver).
- User reported successful 3-terminal manual TCP tests.

## Pending until teammates deliver
- UDP presence/status/timeout and discovery-driven `/list`.
- Typing-safe final CLI and `/send` command.
- Real file sender/receiver, progress, downloads, interruption cleanup.
- Integration tests, physical LAN demo, Wireshark captures, final report.

## Leader's next checkpoints
1. Ensure GitHub Actions passes on main and PRs.
2. Publish module interface contract and issue assignments.
3. Review Member 2/3 PRs and merge after tests.
4. Coordinate two-machine demo, capture evidence and finalize report.
