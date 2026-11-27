---
name: fix-it
description: "Fix the one problem your last report named (a gap, a mismatch, something left undone or still showing the old state), then prove it from the user's side. Use when the user types /fix-it, or replies \"fix it\", \"fix that\" or \"yes, fix it\" right after a report that named a problem. Diagnoses first, backs up before overwriting, makes the smallest reversible fix, verifies what the user actually sees, and reports how to undo it. Not for every open item (/go) or a plan (/step-by-step)."
capability: "Diagnose and fix the single problem the latest report named, reversibly, and verify the result the user observes."
side_effect_level: remote_write
approval_required: true
requires_tools: "Read-only inspection tools first; then the project's own build, test and git/gh commands for repository fixes."
output_schema: "One line on what was wrong, what changed with paths, how it was verified, how to undo it, and anything still not done with a paste-ready command."
risk_class: medium
---

# Fix it

`/fix-it`, or a plain "fix it" right after a report, means: **fix the problem your last message named, and
prove it from the user's side.** It approves that one fix and nothing else.

How this differs from neighbours:
- `/fix-it` fixes the single problem the latest report named.
- `/go` takes the recommended options and finishes every open item.
- `/step-by-step` carries out a plan, one verified step at a time.
- `/next-steps` reports where the work stands; it doesn't change anything.
- `systematic-debugging` is the deeper root-cause loop for a failing test or a bug in code.

## 1. Name the target

- Take the problem from your latest message: something left undone, a mismatch, a "still shows X", a
  "not on this machine". Quote it in one line before doing anything.
- If that message named several, fix the one the user pointed at. Otherwise take the one you flagged as
  left undone. If it's still unclear, ask once.
- If your last message named no problem, say so and stop. Don't go looking for something to fix.

## 2. Diagnose before touching anything

- Look first, read-only. Find what the user actually sees and why. For a desktop shortcut with an old icon,
  read the shortcut's target and icon location, the icon file's date, and which icon the target embeds.
- Before acting, write two lines: the fix, and the **success check**. The check is the user's view, not your
  build: the shortcut's fields read back, the version the installed binary prints, the page as served.
- Fix the cause where it lives. Repository content goes through the project's branch and PR workflow (and
  its ticket, in a tracked project). Machine-local state (installs, shortcuts, notes or config outside a
  repository) is fixed in place, with a backup.

## 3. Keep it reversible

- Look at each target before writing. Never overwrite without a copy: `<file>.bak-<date>` beside it, or a
  dated backup folder for a set of files such as shortcuts.
- When a cache is keyed on the path, add a new file instead of rewriting the old one. Explorer, for
  example, keeps showing a cached icon until the shortcut points at a new file name.
- Install builds outside git checkouts, so a branch switch or a clean can't break what the user launches.
- Leave the old version where it is. Say that it's no longer used and is safe to delete; deleting it is the
  user's call.

## 4. Fix, then verify what the user sees

- Make the smallest change that clears the problem. No drive-by cleanups.
- Run the success check and read the real result. Read things back rather than trusting a write: the
  shortcut after it's saved, the binary's own `--version`, the icon the exe actually embeds.
- If the check fails, find the cause and try again. After about three real attempts, stop and report
  what you learned.

## 5. Limits

`/fix-it` approves local, reversible changes for this one problem, plus commits on a branch, a push
without force, and a PR. It doesn't approve:

- merging, force-pushing, or deleting user data;
- edits to permission policy or harness settings;
- changes in another repository, unless the problem was named there;
- anything the problem didn't name.

When a hook or deny rule blocks a step, don't reword the command. Hand the user the exact command to run
themselves (`! <command>` in Claude Code), and make it paste-exact:

- the full 40-character SHA for `gh pr merge --match-head-commit` (a short SHA is rejected);
- quoted values that start with `#`, such as `--tint "#6A8759"` (Bash reads an unquoted `#` as the start
  of a comment and silently drops the argument);
- the identity a tool requires, such as `--actor human:<name>` where agent identities may not force.

Don't drive a GUI on a desktop the user is using. Stop if the foreground window changes.

## 6. Report

Report once, briefly:

```markdown
**Fixed:** <the problem, in one line>

- **Changed:** <paths, one per line>
- **Verified:** <the success check and its result>
- **Undo:** <backup location or revert command>
- **Not done:** <anything left, with a paste-ready command>
```
