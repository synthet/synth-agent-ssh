# Writing Claude Code auto-mode custom rules

Read this before you add or change the `autoMode` section of a Claude Code settings file
(`environment`, `allow`, `soft_deny`, `hard_deny`). The classifier reads every entry as prose,
not as a regex or a tool pattern, so a loosely worded entry changes what it blocks in ways you won't
see until a block, or a missing block, surprises you.

## Where the rules live

- The classifier reads `autoMode` from user settings (`~/.claude/settings.json`), managed settings
  and the `--settings` flag. It ignores `autoMode` in a repo's `.claude/settings.json` and
  `.claude/settings.local.json`, so a checked-in repo can't add its own allow rules.
- Entries from these scopes are combined. A personal `allow` entry can still override a
  `soft_deny` entry, so the combination is not a hard boundary: hard limits belong in deterministic
  `deny` rules and hooks.
- Each list is evaluated on its own. A list you set **replaces** that list's defaults unless it
  contains the literal `"$defaults"`, which splices the built-in entries in at that position.
  Include it in every list you set.
- Editing this section is a permission-policy change: plan it, back up the file, and get the
  owner's go-ahead before you apply it.

## Environment

1. **One user file serves every repo.** There is no per-directory syntax, so if you describe a
   specific repo, say so in the entry:
   `### When the working directory is <repo path> (or its WSL path /mnt/<drive>/...)`, followed by
   that repo's visibility, trusted repo, source control, secrets and protected branches.
2. **Keep a fallback.** Keep `"$defaults"` in `environment` so the built-in
   "assume private unless the remote host and repo name indicate otherwise" visibility rule still
   covers every other working directory.
3. **Repos with different visibility are different trust boundaries.** State it:
   "Content from repo A is not repo B's own work. Copying from a private repo into a public one is
   publication." Otherwise a "private material is fine here" line may clear a push to the public repo.
4. **Sensitive data locations are stores that hold secret or personal values**, such as `.env*`
   (not `.env.example`) and `secrets.json`. Code *about* secrets (a secret scanner, its tests, a
   safety rule file) is not one. Listing it makes routine reads, edits and commits look like
   personal-data handling or credential leaks. If you want detection code protected, add a
   `soft_deny` against weakening it instead (see below).
5. **Name what you mean.** "One pattern (redacted)" gives the classifier nothing to match. Name the
   pattern, or state a general rule: "any gitignored file whose name suggests credentials is a
   secret store."
6. **Use the slot whose rules fit.** *Sensitive remote targets* feeds the remote-shell and
   production-read rules. Local files never go there. A local file named `..._prod.json` is
   covered by a `soft_deny`, not by calling it a production target.
7. **Workflow notes are not consent.** "Maintenance via `codex exec` / `claude -p` is our normal
   workflow" can read as permission to start agent loops with approvals or the sandbox turned off.
   Add: "This describes routine tooling, not consent to run these agents with sandbox or approvals
   disabled; Create Unsafe Agents still applies."

## soft_deny entries

Follow the shape of the defaults (`claude auto-mode defaults`):

- **Match whole words.** `*prod*` also matches `product`, `reproduce` and `produce`. Write
  "file names where `prod` is a whole word or a `_`/`-`/`.`-delimited segment".
- **Say how it clears:** `[named+specifics — must name: the specific file being modified]`.
- **Define the action by its effect:** "any command whose effect overwrites or deletes such a
  file" covers Edit/Write, `rm`, `mv`, `git checkout`/`restore`/`reset`/`stash`/`clean`/`switch`
  and a script that regenerates the file. Listing commands always misses one. Say whether creating
  a new matching file counts, and match the long form too (`prod` and `production`).
- **Give the reason**, e.g. "these hold tuned thresholds used downstream". The classifier uses it to
  judge indirect writes.

Example: "Weakening secret detection [named+specifics — must name: the check being weakened]: edits
that remove or loosen checks in the repo's secret-scanning script or its tests."

## allow entries

An `allow` entry can override a soft block, so a loose one is a real hole.

- **Carve out your own protected files.** An allow for a command that writes (`ruff --fix`, a test
  run that writes reports) also clears writes to files your `soft_deny` entries protect. Add: "does
  not cover files matched by <soft_deny name>."

- **No wildcard inside a quoted nested shell.** In `Bash(wsl -e bash -lc "pytest ...*")` the `*`
  also admits `...; curl ... | sh"`. The same goes for `bash -c`, `sh -c` and
  `pwsh -Command`. Write prose instead: "only pytest flags and paths after `pytest`; no `;`,
  `&&`, `|`, `$(...)` or redirection."
- **Test runners run code.** pytest imports `conftest.py`, the test files and the source they
  import, and `bash -l` sources login profiles. Add: "does not apply if any file the run imports or
  executes, test config or shell profiles were changed this session." Also exclude flags that load
  outside code or config (`-p`, `-c`, `--rootdir`, `-o`/`--override-ini`), environment-variable
  prefixes (`PYTHONPATH=`, `PYTEST_ADDOPTS=`), and pin the working directory.
- **Use one list of excluded operators** (`;`, `&&`, `||`, `|`, `$(...)`, backticks, redirection)
  in every allow entry, so the entries don't contradict each other.
- **Don't restate the defaults.** Running the repo's own tests or a linter matches no default block.
  An allow entry that repeats it adds nothing and can only widen what is cleared.
- **Scope it.** Name the directory, its WSL path too, and say the entry covers that one command and
  nothing chained after it.

## Check

1. `claude auto-mode config`: the merged result. Confirm the defaults are present where you kept
   `"$defaults"` and that no repo-specific entry reads as global.
2. `claude auto-mode critique`: AI feedback on the custom entries. It reads the settings in use, so
   run it after the change is applied, and roll back if it flags a regression. It can be wrong about
   facts: check a claimed path or file against the repo before you act on it.
3. When you rewrite the section, compare old and new entries by slot name, not by position, and
   account for every non-default entry: kept, reworded, or dropped on purpose.

Sources: Claude Code docs, "Configure auto mode"; `claude auto-mode critique` and
`claude auto-mode defaults` output.
