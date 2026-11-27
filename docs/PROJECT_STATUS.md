# Project status — 2026-11-27

## Integrated implementation
- TCP Core, UDP discovery and typing-safe CLI, file transfer and integration polish are merged into `main` (PRs #4, #5 and #6).
- Verified implementation commit: `94b9736a95add5d73346612bc5f663486f8b8bcc`.
- [GitHub Actions run 45931911100](https://github.com/vinhdu1233-tech/lan-chat-socket/actions/runs/45931911100): all six matrix jobs passed; Ubuntu Python 3.12 log confirms 56 tests, OK.
- Automated test counts: protocol 7, chat 9, discovery 6, CLI 6, file transfer 13, errors 13, integration 2.
- UDP presence uses versioned JSON on 9999, announcements every 3 seconds and expiry after 10 seconds; CLI supports safe redraw, progress throttling and file-received notices.

## Submission evidence
- Two real Wireshark screenshots captured on 27 November on one Mac (Wi-Fi UDP and loopback TCP). [Capture analysis](evidence/README.md) records observed frames and ports.
- The 10-page English report with both screenshots has been updated locally to the 56-test baseline. [Markdown companion](PROJECT_REPORT.md) is available; the actual PDF/DOCX and standalone PNGs still need to be uploaded.
- [Physical LAN acceptance record](evidence/LAN_ACCEPTANCE.md) is ready but has no physical two-computer PASS claims.
- [Live demo plan](DEMO_AND_REPORT.md) is ready for rehearsal.

## Remaining
1. Upload formatted report and two original screenshots to the repository (no unfiltered pcapng files).
2. Test on two physical computers, record evidence and outcomes; correct any failures.
3. Rehearse and deliver the required 10-minute live demo.
4. Review submission checklist in Issue #3. Close only when all evidence and delivery requirements are satisfied.

The local captures and automated CI do not prove connectivity between physical LAN computers.
