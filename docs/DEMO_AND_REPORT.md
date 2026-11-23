# Report and live demonstration

## Required submission
1. Source with README covering install, run and tests.
2. Report of 5–10 pages: architecture, thread model, protocol format, challenges, solutions and tests.
3. Wireshark screenshots proving UDP broadcast and TCP three-way handshake with written explanation.
4. Live 10-minute demo on **at least 2 computers** connected to the same LAN.

## Report outline (5–10 pages)
- Title, team members, objectives and scope.
- P2P architecture, UDP vs TCP rationale and module ownership.
- Application-layer protocol: discovery messages, framed JSON headers, exact payload reads, handshake.
- Concurrency: accepting connections, receiver workers, locks, event queue, separate file sender, UI redraw.
- Implementation: commands, status/expiry, multi-peer history/unread, file progress.
- Error handling and test evidence, Wireshark captures, problems/solutions.
- Limitations and conclusion.

Each member drafts their technical section. Leader reviews final report for alignment with actual code.

## 10-minute demo
| Time | Person | Content |
|---|---|---|
| 0:00–1:30 | Leader | P2P architecture and protocol |
| 1:30–3:00 | Member 2 | Discovery and status |
| 3:00–5:00 | Leader | Chat, unread, 3 peers, reconnect |
| 5:00–7:00 | Member 3 | File transfer during chat, progress |
| 7:00–8:30 | Members 2+3 | Typing-safe UI and errors |
| 8:30–9:30 | Leader | Wireshark filters and TCP handshake |
| 9:30–10:00 | All | Summary and individual contributions |

Filters: `udp.port == 9999`, `tcp.flags.syn == 1` (for handshake start), TCP destination port as appropriate. Evidence still needs to be captured during a real run.
