---
name: Member 2 — UDP Discovery + Console
about: Implement UDP peer discovery, status and production typing-safe CLI
title: "[Member 2] UDP discovery, online status and console"
labels: []
assignees: []
---

## Owned files
`discovery.py`, `cli.py`, `tests/test_discovery.py`, `tests/test_cli.py`.

## Deliverables
- [ ] UDP 9999 broadcast every 3 seconds; listen/track peers and expire after 10 seconds.
- [ ] Use the same `peer_id` as TCP `ChatNode`; statuses online/away; event notifications.
- [ ] CLI: `/list`, `/chat`, plain-text messages, `/send`, `/leave`, `/status`, `/help`, `/quit`.
- [ ] Preserve in-progress input when remote message arrives.
- [ ] Integrate with the existing `ChatNode` API and Member 3's `send_file` interface.
- [ ] Add tests, screenshots/logs, error handling and PR to main.

## Criteria
Two physical machines discover one another; status changes propagate; stale peer expires at 10 s; multiple peers and UI input remain stable.

**Read:** `docs/INTEGRATION_CONTRACT.md` and `docs/TEAM_TASKS.md`.
