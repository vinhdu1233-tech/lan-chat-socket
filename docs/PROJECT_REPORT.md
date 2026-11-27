# LAN Chat & File Sharing — Technical report (Markdown companion)

Python Socket Programming Project · November 2026  
Implementation baseline: [94b9736](/vinhdu1233-tech/lan-chat-socket/commit/94b9736a95add5d73346612bc5f663486f8b8bcc); [CI run 45931911100](https://github.com/vinhdu1233-tech/lan-chat-socket/actions/runs/45931911100).

| Role | Name | Responsibility |
|---|---|---|
| Leader | Lương Vĩnh Du | TCP Core, protocol, integration, report |
| Member 2 | Lê Minh Tuấn Tú | UDP discovery and typing-safe console |
| Member 3 | Bùi Minh Trí | TCP file transfer and reliability tests |

This is the online companion to the locally prepared 10-page report. Its physical LAN and live demonstration sections remain pending.

## 1. Introduction and objectives
The application runs the same Python 3.10+ program on each peer. UDP offers connectionless periodic broadcast to discover peers and distribute online/away status. TCP provides an ordered byte stream for chat and file data. No central server or third-party runtime dependency is required. The objectives include native sockets, a custom wire protocol, multithreaded communication, responsive input, progress and error handling.

## 2. Architecture
Each ChatNode acts as a TCP listener and can initiate connections as a client. DiscoveryService supplies the observed IP, peer ID and TCP port. The CLI opens TCP on demand and chooses an active conversation. Independent receiver workers keep other connections available. File transfers use their own sockets so they do not share the chat byte stream. main.py starts discovery, registers the file receiver, runs the CLI and stops services on exit.

| Module | Responsibility |
|---|---|
| protocol.py | Framing, validation and exact reads |
| tcp_chat.py | Connection identity, chat, histories, unread and events |
| discovery.py | UDP presence, status and expiry |
| cli.py | Commands and synchronized interactive display |
| file_transfer.py | Chunked streaming, progress, safe publication and cleanup |
| tests/ | Protocol, chat, discovery, CLI, file, error and end-to-end verification |

## 3. Application protocol
A TCP frame begins with four unsigned big-endian bytes denoting the length of a UTF-8 JSON header, then the header and any declared payload. For example, header `{"type":"MESSAGE","size":2}` is 27 bytes, so prefix 0x0000001B is followed by the JSON and the two payload bytes Hi. TCP is a stream: recv() may return less than requested. receive_exact() loops until enough bytes arrive or raises ConnectionClosed. send_frame() writes the header only; payload is sent separately.

HELLO and HELLO_ACK exchange version 1, peer_id, name and tcp_port after the transport handshake. MESSAGE includes size; FILE_OFFER contains sender_id, filename and size on an independent TCP socket; BYE closes chat and ERROR reports protocol/application errors. Limits are 16 KiB header, 1 MiB chat payload and 1 TiB declared file size. Identity consistency and self-connection rejection are not authentication.

## 4. Discovery and CLI
DiscoveryService binds UDP port 9999, enables broadcast and sets reuse options where supported. It sends JSON HELLO with version 1, peer_id, name, tcp_port and status to 255.255.255.255 every three seconds, waking early on a status change. recvfrom() supplies the observed address. The listener validates packets, ignores self, keys records by peer ID and expires entries after 10 seconds using a monotonic clock. The CLI supports /list, /chat, /send, /leave, /status, /help, /quit and plain text. It maintains an input buffer and redraws it under a screen lock when an event arrives. Keyboard input uses msvcrt on Windows and termios/tty on POSIX; non-interactive fallback uses input().

## 5. File transfer and error handling
The sender validates a regular file, opens a dedicated connection and writes FILE_OFFER followed by 64 KiB chunks with sendall(). The CLI uses a background worker and throttles progress to avoid flooding the terminal. Receiver streams exact bytes to a temporary .part file, publishes a unique filename after completion and emits a file_received notice. Invalid names, path traversal, bad sizes, missing files, disconnects, timeout and disk failures are handled; partial files are removed. Duplicate destinations use unique names and a commit lock. SHA-256 verifies byte identity in tests. Sender 100% does not prove receiver disk success: there is no application-level completion ACK.

## 6. Thread model and synchronization
The main thread processes keyboard input. UDP broadcaster/listener handle periodic presence and expiry. A TCP acceptor dispatches incoming workers, with one receiver per chat; file workers handle independent sockets. The console event worker drains thread-safe queues. ChatNode's RLock protects connections, history, unread, active selection and worker tracking; per-connection write locks serialize header and payload. Discovery and terminal state have separate locks. A deterministic peer-ID rule resolves duplicate connections. Histories are keyed by peer ID; inactive conversations increment unread and activation resets it.

## 7. Test results and packet evidence
The verified CI run passed six jobs (Ubuntu/macOS/Windows × Python 3.10/3.12). Ubuntu Python 3.12 logs report 56 tests and OK. Breakdown: protocol 7; chat 9; discovery 6; CLI 6; file transfer 13; errors 13; integration 2. Tests cover framing, bidirectional chat, unread, expiry/status, typing redraw, file integrity, concurrent transfer/chat, failure recovery and end-to-end integration.

Actual screenshots were captured locally on a Mac on 27 November. [Detailed Wireshark analysis](evidence/README.md): UDP frame 5019, 133-byte versioned HELLO, ports 9999, IPv4 destination 255.255.255.255; TCP frames 50–52 show SYN, SYN-ACK, ACK on 58205 ↔ 5002. These captures demonstrate protocol behavior on one computer, not physical cross-machine connectivity. The formatted report includes the two original images; their repository upload is pending. [Physical LAN record](evidence/LAN_ACCEPTANCE.md) remains pending.

## 8. Challenges, solutions and conclusion
TCP fragmentation is handled through length-prefixed frames and exact reads. Per-socket locks prevent write interleaving; peer-ID arbitration handles simultaneous connections. Safe redraw protects typed input. Temporary downloads and unique names avoid partial final files and overwrites. PR #4 initially failed because a test incorrectly assumed an absolute order across independently handled chat directions; the test was corrected and later CI passed. Remaining limitations include RAM-only history, session IDs, no authenticated/encrypted transport, no final file ACK and dependence on LAN broadcast/firewall policy. A successful automated suite is not a substitute for the required two-computer demonstration.

## References
- Socket Programming Project: LAN Chat & File Sharing (Command-Line), assignment brief, sections 3–8.
- [Repository](https://github.com/vinhdu1233-tech/lan-chat-socket); [PR #4](https://github.com/vinhdu1233-tech/lan-chat-socket/pull/4), [PR #5](https://github.com/vinhdu1233-tech/lan-chat-socket/pull/5), [PR #6](https://github.com/vinhdu1233-tech/lan-chat-socket/pull/6).
- [CI evidence](https://github.com/vinhdu1233-tech/lan-chat-socket/actions/runs/45931911100).
