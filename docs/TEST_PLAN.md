# Verification and acceptance plan

Leader's existing automated command:
```bash
python3 -m unittest discover -s tests -v
```
Baseline on 2026-11-23: 16/16 PASS locally, before integration. Run CI on every PR. Do not label tests PASS merely because the plan exists.

## TCP Core manual smoke test
Start Alice (5001), Bob (5002), Charlie (5003) in three terminals. Alice connects to Bob via `/connect 127.0.0.1:5002`. Charlie also connects to Bob. While Bob's active chat is Alice, Charlie sends two messages; verify unread counter 2 then `/chat Charlie` displays history and unread resets. Exit Alice and verify Bob continues chatting with Charlie. Test `/leave`, reconnect and long UTF-8 messages.

## Final integration acceptance (all currently PENDING)
| ID | Test | Expected result |
|---|---|---|
| U1 | Two physical LAN peers start | UDP discovery in `/list` |
| U2 | Change `/status away` | Remote peer shows away |
| U3 | Terminate a peer | Other peer expires it in ~10 s |
| U4 | Run 3 local instances | All users discovered where OS permits port reuse |
| T1 | Chat bidirectionally | Both receive full UTF-8 text |
| T2 | Third peer sends while chat active | Unread/history correct |
| T3 | Incoming text during typing | Input preserved |
| F1 | Send PNG/PDF/10 MB binary | Saved in downloads, SHA-256 matches |
| F2 | Chat while file is streaming | Chat remains responsive |
| F3 | Interrupt transfer | Partial file removed, error shown |
| E1 | Connect offline / bad command | No crash, useful error |
| W1 | Capture UDP broadcast | `udp.port == 9999`, annotated screenshot |
| W2 | Capture TCP handshake | SYN, SYN-ACK, ACK identified |
| D1 | Complete demo | 10 minutes, >= 2 physical computers |

Record test date, OS, Python version, steps, expected and actual outcome under `docs/evidence/`. Never fabricate Wireshark evidence.
