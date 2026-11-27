# Tasks: synth-agent-ssh MCP service (read-only v1)

Spec: [spec.md](spec.md). One PR per task. Never merge your own PR.

| ID | Task | Depends on | Done when |
|---|---|---|---|
| T-1 | Vendor `cross_pc_ssh.py` from synth-agent-framework at a pinned commit, with `VENDORED_FROM` and `scripts/check_vendor.py` | — | AC-8: the check passes at the pin and fails on a one-byte edit |
| T-2 | Config loader: peers (alias allowlist) and local roots; refusals before any subprocess | T-1 | AC-3, AC-9: unit tests for unknown peer, path outside roots, missing config |
| T-3 | Subprocess runner: argument list, no shell, timeouts, output cap, audit line | T-1 | AC-2, AC-5, AC-6, AC-7: unit tests with a fake helper |
| T-4 | MCP server with the seven tools and their input schemas | T-2, T-3 | AC-1, AC-4: a schema snapshot test; an MCP client lists exactly seven tools |
| T-5 | Harness setup docs: `.mcp.json` example, permission rules (`ssh_agent` as ask), read-only notes | T-4 | README and `docs/` examples; checks pass |
| T-6 | Live smoke between two paired PCs: every tool, refusals, and a read-only agent asked to write (no file appears) | T-4 | Evidence in the PR, with neutral peer labels |
