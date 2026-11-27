# Report and 10-minute live demonstration

## Submission
1. Source and README (install, run, test).
2. Technical report of 5–10 pages (architecture, thread model, protocol, challenges and solutions). The formatted 10-page report with local capture evidence has been prepared locally; see [Markdown companion](PROJECT_REPORT.md).
3. Required Wireshark screenshots: UDP broadcast and TCP three-way handshake with explanations. [Observed packet analysis](evidence/README.md) is recorded. Original PNGs remain to be uploaded.
4. Ten-minute live demonstration on at least two physical computers. Pending.

## Setup before rehearsal
Use two physical computers on the same LAN. Run Alice on port 5001, Bob on 5002, and optionally Charlie on 5003 on either computer. Open an interactive terminal per peer, run the full test suite, prepare a PDF and a large test file, and verify firewall rules. Use /list then /chat, not the old development-only /connect command.

| Time | Owner | Demonstration |
|---|---|---|
| 0:00–1:30 | Leader | Explain P2P and UDP/TCP; show project modules and framing |
| 1:30–3:00 | Member 2 | /list, /status away, peer expiry |
| 3:00–5:00 | Leader | /chat, two-way UTF-8 chat, third-peer unread, /leave and reconnect |
| 5:00–7:00 | Member 3 | /send a file, progress, receive notice, downloads and checksum; chat during transfer |
| 7:00–8:30 | Members 2 and 3 | Preserve typing during incoming message; invalid command/missing file |
| 8:30–9:30 | Leader | Show actual UDP and SYN/SYN-ACK/ACK capture; distinguish application HELLO |
| 9:30–10:00 | All | 56-test CI baseline, individual contributions, limitations and conclusion |

Record the actual results in [LAN_ACCEPTANCE.md](evidence/LAN_ACCEPTANCE.md). Capture filters: `udp.port == 9999`; isolate a new TCP connection with `tcp.stream == N` after identifying its SYN. Do not claim completed live demo until performed.
