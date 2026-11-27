# Verification & Wireshark Evidence — Du & Tri (2026-11-27)

- **Date:** 2026-11-27
- **Environment:** Windows (64-bit), Python 3.12.10, Wireshark / `tshark`
- **Setup:** Two live peer processes on one host (`main.py --name Du --port 5001` and `main.py --name Tri --port 5002`), captured on `Adapter for loopback traffic capture` (`udp port 9999 or tcp port 5001 or tcp port 5002`, 1,097 frames total, 0 unrelated background traffic).
- **Honest scope note:** This capture demonstrates the real running application and real OS TCP/UDP packets between two terminals on a single machine. For final submission, also repeat the live demo across at least **two physical computers** on the same LAN per `docs/TEST_PLAN.md`.

## Captured Evidence Files

| File | Filter / Scope | What it proves |
|---|---|---|
| [01_udp_discovery_9999.png](01_udp_discovery_9999.png) | `udp.port == 9999` (Frame 5 selected) | Periodic 3s UDP broadcast to `255.255.255.255:9999` with JSON `"type":"HELLO","version":1`; Frame 5 (`4.416s`) shows immediate re-broadcast when Tri switches `/status away`; Frames 1090–1097 show only Du broadcasting after Tri quits, triggering 10s expiry. |
| [02_tcp_chat_handshake_stream0.png](02_tcp_chat_handshake_stream0.png) | `tcp.stream == 0` (Frame 7 selected) | TCP 3-way handshake (`57377 -> 5002`: `[SYN]`, `[SYN, ACK]`, `[ACK]` in Frames 7–9) followed by application `HELLO` / `HELLO_ACK` and bidirectional UTF-8 `MESSAGE` frames; stream stays open until Frame 1091 (`10.668s`). |
| [03_tcp_file_offer_stream3.png](03_tcp_file_offer_stream3.png) | `tcp.stream == 3` (Frame 111 selected) | Separate TCP connection on a distinct ephemeral port (`57380 -> 5002`) with its own 3-way handshake (Frames 108–110), followed by Frame 111 carrying the 4-byte big-endian length (`00 00 00 71` = 113 bytes) + JSON `{"type":"FILE_OFFER","sender_id":"140efa2f2b6a45a097fc220fda4297b1","filename":"sample_20mb.bin","size":20971520}`. |
| [04_tcp_file_segments_and_fin.png](04_tcp_file_segments_and_fin.png) | `tcp.stream == 3` (Frame 1086 selected) | 20 MiB payload streamed across **982 TCP packets** (`Seq` reaching `20971638`) and closed cleanly via `[FIN, ACK]` / `[ACK]` handshake (Frames 1086–1089) while chat `tcp.stream == 0` remains active. |
| [05_du_tri_two_terminals_and_sha256.png](05_du_tri_two_terminals_and_sha256.png) | Verbatim 2-terminal transcript + SHA-256 | End-to-end live run of **Du** and **Tri**: UDP discovery, `/list`, `/status away|online`, UTF-8 chat, UTF-8 PDF transfer + duplicate rename (`báo cáo demo (1).pdf`), 20 MiB transfer with throttled 10% progress + concurrent chat messages interleaved mid-transfer, `[File from Du]` receiver notifications, error recovery on invalid command/missing file, 10s UDP expiry, and exact SHA-256 matches. |

## Verified SHA-256 Checksums (Source vs `downloads/`)
- `báo cáo demo.pdf` (524,310 bytes): `911a53f4dc83d7b27c590e0161560c01006528090283177153261a77cf813d42` — **MATCH**
- `báo cáo demo (1).pdf` (524,310 bytes): `911a53f4dc83d7b27c590e0161560c01006528090283177153261a77cf813d42` — **MATCH**
- `sample_20mb.bin` (20,971,520 bytes): `bca0b79c6200c99b568cb51f6d5923e1ae3ac971dfb0714e78676748c5962ba9` — **MATCH**
