# GitHub workflow for the LAN Chat team

Repository: https://github.com/vinhdu1233-tech/lan-chat-socket

## Collaborators
Owner invites both members via GitHub repository **Settings → Collaborators → Add people**, using the exact GitHub usernames. Do not share passwords or access tokens.

## Development
```bash
git clone https://github.com/vinhdu1233-tech/lan-chat-socket.git
cd lan-chat-socket
python3 -m unittest discover -s tests -v
git switch -c feature/udp-cli
# Or: git switch -c feature/file-transfer
# edit owned files, then:
git add .
git commit -m "feat: add assigned module"
git push -u origin feature/udp-cli
```

Open a PR targeting `main`. Each PR must link its GitHub Issue, explain changed files, test results and limitations. Request Leader review. **No direct push to main**, as an agreed team workflow.

## PR acceptance
- No undocumented change to protocol/leader files.
- `python3 -m unittest discover -s tests -v` passes.
- New tests and evidence for changed behavior.
- Reviewer resolves comments before merging.
- Merge only after checks; update local main with `git pull`.

## GitHub CI
`.github/workflows/python-tests.yml` runs unit tests on Linux/macOS/Windows. CI proves the existing automated tests, not final LAN or Wireshark behavior. Branch protection may not be enforceable on all repository plans; follow review agreement even without enforced rules.

## Privacy
Repository was observed as **public** at setup. Owner can change visibility under Settings → General → Danger Zone → Change repository visibility, if course policy requires private coursework.
