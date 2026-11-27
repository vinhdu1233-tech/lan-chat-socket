# Verification and acceptance plan

Integrated automated command:
```bash
python3 -m unittest discover -s tests -v
```
Verified implementation baseline `94b9736`: 56 tests passed in the Ubuntu Python 3.12 log and all six CI jobs passed in [run 45931911100](https://github.com/vinhdu1233-tech/lan-chat-socket/actions/runs/45931911100). Run CI on every PR. Physical LAN results must be recorded in [LAN_ACCEPTANCE.md](evidence/LAN_ACCEPTANCE.md).

## Integrated application smoke test
Start Alice (5001), Bob (5002), Charlie (5003) in interactive terminals. Use `/list` to discover peers, then `/chat Bob` or `/chat Alice`. Verify two-way chat, unread from Charlie, switching history, /leave and reconnect. The development-only `/connect` command is not needed.

## Final integration acceptance (physical LAN checks pending)
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
| W1 | Capture UDP broadcast | Locally captured; see [observations](evidence/README.md); PNG upload pending |
| W2 | Capture TCP handshake | Locally captured; frames 50–52 identified; PNG upload pending |
| D1 | Complete demo | 10 minutes, >= 2 physical computers |

Record test date, OS, Python version, steps, expected and actual outcome under `docs/evidence/`. Never fabricate Wireshark evidence.
