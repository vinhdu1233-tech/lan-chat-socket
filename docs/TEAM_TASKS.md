# Team tasks — 3 members

**Read [the integration contract](INTEGRATION_CONTRACT.md) before writing code.** Do not modify another owner's files without a reviewed proposal.

## Leader — TCP Core & Integration
Owned: `protocol.py`, `tcp_chat.py`, `main.py`, `tests/test_protocol.py`, `tests/test_chat.py`, `docs/INTEGRATION_CONTRACT.md`.
- Implemented framed TCP protocol, P2P chat listener/client, HELLO/HELLO_ACK, multi-peer threads, unread/history, disconnect and reconnect.
- Local baseline: 16/16 unit tests PASS. User confirmed manual three-terminal chat/unread/disconnect behavior.
- Pending: integration PR review, two-computer regression testing, final report, Wireshark, 10-minute demo.

## Member 2 — UDP Discovery & Final Console UI
Files: `discovery.py`, `cli.py`, `tests/test_discovery.py`, `tests/test_cli.py`.
- UDP broadcast `9999` every 3 seconds; listen on same port.
- Maintain peer list: `peer_id`, `name`, `host/ip`, `tcp_port`, `status`, `last_seen`; remove after 10-second timeout.
- `/list` uses discovered peers, `/status online|away`; notify online/offline.
- Implement required commands `/list`, `/chat <name|number>`, plain text chat, `/send <path>`, `/leave`, `/status`, `/help`, `/quit`.
- Incoming events must not destroy a partially typed input line (e.g. `prompt_toolkit` / `patch_stdout`).
- Use `ChatNode.events`, `ChatNode.connect_to_peer` and the published integration contract.
- Deliver Python module, tests, manual two-peer test notes and PR; no changes to TCP Core without review.

**Acceptance:** two/three peer discovery, online/away, 10-second expiration, typing-safe prompt, command handling, duplicate name/offline peer behavior.

## Member 3 — File Transfer & Reliability Tests
Files: `file_transfer.py`, `tests/test_file_transfer.py`, `tests/test_errors.py`, Wireshark evidence contribution.
- Open separate TCP socket, send `FILE_OFFER`, stream file in chunks, show percentage and keep chat responsive.
- Receiver validates basename/size, saves to `downloads/`, protects against overwriting; deletes partial files on error or interrupted connection.
- Test empty/Unicode name/PDF/10 MB binary file, missing file, mid-transfer disconnect, duplicate filename and file checksum.
- Expose `send_file(node, peer_id, path, progress_cb=None)` and `receive_file(sock, header, address)`.
- Receiver owns file socket while handler runs; set a bounded inactivity timeout. Coordinate optional completion ACK with Leader.
- Deliver sender/receiver, automated tests, Wireshark evidence and PR.

**Acceptance:** file byte-for-byte match, correct progress, saved in downloads, chat operational during transfer and error recovery.

## Review policy
Feature branches: `feature/udp-cli`, `feature/file-transfer`. PR → check CI + owned-file changes + tests → Leader review → merge to main. Never commit directly to main as a team practice.
