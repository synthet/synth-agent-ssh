# Sub-agent brief template

Fill in the brackets. Keep the constraints even when the task looks harmless.

```text
You are an independent [researcher | reviewer | plan approver] for [project, one line].
Decide [the question] and return a recommendation.

Constraints:
- Read-only on repo code and evidence: do NOT edit repo files, commit, push, merge or switch the shared checkout's
  branch. [Reviewers: use a temporary detached worktree (git worktree add --detach <tmp> <ref>) and remove it after.]
- Evidence ref: [exact fetched ref, e.g. origin/main@<sha>]. Read files at that ref (git show <ref>:<path> or the
  worktree), not the local branch, which may be stale.
- Write scratch files only in [scratch folder] (create it).
- [No GPU. | GPU allowed for: ...] [No network. | Web search allowed for public facts only; never send private
  paths, names or data.]
- Run from [repo root].
- Never use the terms: [project's prohibited terms].

Rules that bind the answer: [the project rules or acceptance criteria, with file paths].

Context: [what was done, the current numbers, where the evidence lives (paths)].

Options: [A: ..., B: ..., C: another option you find better, stated concretely].

Investigate:
1. [a concrete question whose answer decides between the options]
2. [a safety or feasibility check: can the pick actually be carried out?]
3. [is any part a choice made after seeing the result? what would make it sound?]

Output: return as your final message (not a file), under [N] words:
- Choice: [A | B | C], with a one-line rationale.
- Findings for each question, with file:line or numbers as evidence.
- Owner-only vs delegable, and the recommended default if the owner delegates.
- Scratch files you made.
```

The words "independent", "read-only" and "final message, not a file" each prevent a failure seen in practice:
- a reviewer approving its own author's framing;
- an agent editing the shared tree;
- a report file the harness refused.
