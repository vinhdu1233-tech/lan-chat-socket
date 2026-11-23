---
name: Member 3 — TCP File Transfer
about: Implement chunked TCP file transfer and reliability tests
title: "[Member 3] File transfer and reliability"
labels: []
assignees: []
---

## Owned files
`file_transfer.py`, `tests/test_file_transfer.py`, `tests/test_errors.py`.

## Deliverables
- [ ] `send_file(node, peer_id, path, progress_cb=None)`
- [ ] `receive_file(sock, header, address)`
- [ ] Separate socket, `FILE_OFFER` header, chunked file bytes and percent progress.
- [ ] Save to `downloads/`; safe basename; collision handling; delete partial files on failure.
- [ ] Preserve responsive chat while sending; run file send in its own thread.
- [ ] Tests: empty file, Unicode name, binary, 10MB, missing file, disconnect, duplicate name, checksum.
- [ ] Wireshark evidence contribution, PR to main.

**Read:** `docs/INTEGRATION_CONTRACT.md` before coding; agree on any new ACK frame with Leader.
