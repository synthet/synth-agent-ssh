# Spec: synth-agent-ssh MCP service (read-only v1)

Status: Draft, for owner review. Decisions so far:
- public repo (owner, 2026-11-27);
- read-only tools first (Jev, jev-1.14.0, p 0.98);
- thin wrapper over the cross-pc-ssh helper (Jev, p 0.55; owner approved the plan).

## Summary

An MCP stdio server that gives agents the cross-pc-ssh helper's verbs as typed tools: locate this
repository's checkout on a paired Windows PC, then read its status, folders, files and git history, or ask a
read-only agent there. The helper from synth-agent-framework (`.claude/skills/cross-pc-ssh/scripts/cross_pc_ssh.py`)
stays the only implementation of the identity guard, path rules and quoting. This server adds tool
schemas, an allowlist of local checkouts and peers, output limits and an audit line per call.

## Users / stakeholders

- Agents in Claude Code, Codex, Cursor or Antigravity that need the same project on another PC. Today they
  have to shell out to the helper and parse its text.
- The owner, who wants peer access to stay scoped to one repository and visible in permission prompts.

## Product scenario

An agent asks "what does the other PC have on this branch?" and gets a structured answer from a tool call.
The owner can allow or deny each tool by name in harness permissions. No tool can change files on the peer
in v1.

## Non-goals

- Any tool that edits files on the peer. A later write tool would be separate, gated by a per-call
  permission rule, and live-tested first.
- Raw remote commands, SSH key or sshd setup, non-Windows peers.
- A second implementation of the helper's guard, quoting or path checks.
- Network listeners: stdio only, no port.

## User stories

- As an agent, I want `locate` and `status` for my current repository on a named peer, so I can compare branches.
- As an agent, I want `ls`, `cat` and read-only `git` on the peer checkout, so I can read without asking the user to copy files.
- As an agent, I want a read-only `agent` tool, so a model on the peer can answer from its checkout.
- As the owner, I want every call limited to configured peers and local checkouts, and logged, so access stays scoped and auditable.

## Acceptance criteria

- **AC-1** The server shall expose exactly these tools over MCP stdio: `ssh_whoami`, `ssh_locate`, `ssh_status`,
  `ssh_ls`, `ssh_cat`, `ssh_git` and `ssh_agent` (read-only), each with a JSON input schema.
- **AC-2** Each tool shall run the vendored helper as a subprocess with an argument list, never through a shell,
  and shall return its stdout, its stderr and its exit code.
- **AC-3** If a tool call names a peer that isn't in the config's peer list, or a local checkout outside the
  configured local roots, then the server shall refuse the call without running the helper.
- **AC-4** The server shall not expose `--allow-edits`, `--path` or a free-form command in any tool.
- **AC-5** If the helper's output exceeds the configured limit (default 200 kB), then the server shall truncate
  it and mark the result as truncated.
- **AC-6** If a call runs past its timeout (default 120 s, 1800 s for `ssh_agent`), then the server shall stop the
  helper process and return a timeout error.
- **AC-7** The server shall append one JSON line per call to a local audit log, holding the time, tool, peer,
  checkout, exit code and output size, never file contents or prompts.
- **AC-8** The vendored helper shall carry the framework commit it came from. A check (`scripts/check_vendor.py`)
  shall fail when its hash differs from that commit's file.
- **AC-9** The tracked files shall contain no host names, IPs, user names or machine paths. The config
  (`~/.config/cross-pc-ssh.json`, shared with the helper) and the audit log live in the user's profile, outside the repo.

## Assumptions and dependencies

- Python 3.11+, the `mcp` SDK (2.x, as jev-mcp uses), the OpenSSH client and key-based ssh to each peer.
- The helper's CLI (verbs, exit codes 2, 3, 4) stays stable. The vendor check catches drift.
- Peers are Windows PCs with Windows PowerShell and git, as the helper requires.

## Decisions (owner, 2026-11-27)

- **Config:** reuse the helper's `~/.config/cross-pc-ssh.json` (override `CROSS_PC_SSH_CONFIG`), adding a `local_roots` list of folders the server may use as local checkouts. Its `peers` keys are the allowlist for AC-3. One file, so the helper and the server can't disagree about peers.
- **License:** MIT (`LICENSE` at the repo root).
- **`ssh_agent` permission:** allowed like the other read-only tools, with no extra prompt by default. The setup docs (T-5) still say it runs a model on the peer and uses the peer's quota, so an owner who wants a prompt can add an `ask` rule.

## Open questions

None.
