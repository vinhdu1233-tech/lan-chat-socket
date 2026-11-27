# Physical LAN acceptance record

**Status: PENDING — to be completed by the team on at least two physical computers.** Local automated tests and Wireshark screenshots do not establish this result.

## Session details
- Date/time:
- Participants:
- Implementation commit:
- Computer A: OS / Python / LAN IP / TCP port:
- Computer B: OS / Python / LAN IP / TCP port:
- Optional third peer (may run on either computer):
- Network and firewall notes:

## Procedure
Run `python3 -m unittest discover -s tests -v` on both computers. Connect both to the same LAN and start Alice on 5001 and Bob on 5002; start Charlie on 5003 for unread tests. Use real interactive terminals, not piped stdin. Allow UDP 9999 and the chosen TCP ports in the firewall.

| ID | Test and expected behavior | Actual result / evidence | Status |
|---|---|---|---|
| U1 | /list shows the other physical peer without manual connection | | Pending |
| U2 | /status away appears on the other peer | | Pending |
| U3 | /quit or terminate; peer expires after about 10 s | | Pending |
| U4 | Third instance discovered | | Pending |
| T1 | /chat Bob; both peers exchange UTF-8 text | | Pending |
| T2 | Charlie sends twice while Bob chats with Alice; unread 2, switch clears | | Pending |
| T3 | Bob receives while typing; typed text remains | | Pending |
| T4 | /leave then /chat reconnects | | Pending |
| F1 | Send PDF and >=10 MiB file; compare SHA-256 and check downloads | | Pending |
| F2 | Exchange chat messages while file transfer remains active | | Pending |
| F3 | Interrupt transfer; no incomplete final file or .part remains | | Pending |
| E1 | Missing file, invalid command, stale peer connection; application remains usable | | Pending |
| D1 | Deliver 10-minute demo on at least two physical computers | | Pending |

For macOS use `shasum -a 256 FILE`; Linux use `sha256sum FILE`; Windows PowerShell use `Get-FileHash -Algorithm SHA256 FILE`. Record both hashes and actual outcomes. Add only relevant screenshots, not unfiltered network traces.

## Sign-off
Leader:
Member 2:
Member 3:
Remaining issues:
