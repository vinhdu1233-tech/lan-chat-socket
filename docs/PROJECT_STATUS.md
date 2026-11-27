# Project status — 2026-11-27

## Published & Merged on GitHub (`main`)
- **Leader (TCP Core):** `protocol.py`, `tcp_chat.py`, `main.py`, `dev_console.py`, `tests/test_protocol.py` (7 tests), `tests/test_chat.py` (9 tests), GitHub Actions CI (`.github/workflows/python-tests.yml`), architecture and integration docs.
- **Member 3 (File Transfer — PR #4 merged):** `file_transfer.py`, `tests/test_file_transfer.py` (13 tests), `tests/test_errors.py` (13 tests) — dedicated TCP socket, `FILE_OFFER` framing, 64 KiB chunked streaming, 0–100% progress callback, UTF-8 & duplicate-safe saving to `downloads/`, `.part` cleanup on errors/timeouts, concurrent chat + SHA-256 verification.
- **Member 2 (UDP Discovery & CLI — PR #5 merged):** `discovery.py`, `cli.py`, `tests/test_discovery.py` (4 baseline tests), `tests/test_cli.py` (5 baseline tests) — UDP port 9999 broadcast every 3s, 10s expiry, `/status online|away`, standard-library typing-safe console UI (`msvcrt`/`termios`), `/list`, `/chat`, `/send`, `/leave`, `/help`, `/quit`.
- **GitHub Actions CI on `main`:** 51/51 tests passing across `ubuntu-latest`, `macos-latest`, and `windows-latest` (Python 3.10 & 3.12).
- GitHub repository: https://github.com/vinhdu1233-tech/lan-chat-socket

## Completed on Integration Polish Branch (`fix/integration-improvements`)
- Receiver-side `file_received` event emission in `tcp_chat.py` and `[File from ...]` display in `cli.py`.
- Throttled and formatted `/send` progress updates in `cli.py` (10% increments up to `100%`, avoiding 160+ spam lines on 10 MB transfers) plus support for both single-quoted and double-quoted file paths.
- UDP `HELLO` `"version": 1` field and version check in `discovery.py`, plus live UDP socket `start()`/`stop()` tests in `tests/test_discovery.py`.
- Full end-to-end integration tests without mocks in `tests/test_integration.py` (2 tests).
- **Automated test status on `fix/integration-improvements`:** **56/56 PASS** locally (`-W default`, 0 warnings) and **6/6 PASS** in GitHub Actions CI.

## Pending Before Final Submission
- Review and merge `fix/integration-improvements` into `main` via Pull Request.
- Physical **two-computer LAN** verification (firewall rules for UDP 9999 and TCP ports, acceptance checklist `U1–U4`, `T1–T3`, `F1–F3`, `E1`, `W1–W2` in `docs/TEST_PLAN.md`).
- Capture and annotate **Wireshark evidence** under `docs/evidence/` (UDP broadcast on port 9999, TCP three-way handshake `SYN`/`SYN-ACK`/`ACK`, separate TCP stream for `FILE_OFFER` and chunked payload).
- Finalize the **5–10-page report** combining all three members' technical sections, test evidence, and Wireshark screenshots.
- Rehearse and deliver the **10-minute live demonstration** on at least two physical computers.

## Next Checkpoints
1. Merge `fix/integration-improvements` PR into `main` and confirm 56/56 CI green on `main`.
2. Run the two-machine LAN test session and record real Wireshark captures in `docs/evidence/`.
3. Assemble and review the 5–10-page final report against actual code and test logs.
4. Rehearse the 10-minute demo following `docs/DEMO_AND_REPORT.md`.
