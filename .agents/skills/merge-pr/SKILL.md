---
name: merge-pr
description: "Merge one GitHub PR: when its CI already passed on the exact head commit, merge it after the same re-checks; when some runs passed and the rest could not start, replay only the ones that didn't; when CI cannot run (Actions cannot start for reasons unrelated to the change, such as billing, spending limit, exhausted minutes or a runner outage; workflows exist but no run ever registered for the head commit; or the repository has no CI at all), prove which, run the workflow's steps (or, with no CI, the project's declared checks) locally in a clean worktree on that commit, then merge pinned to it. Runs only when the user types /merge-pr, with a PR number, URL or branch; with none it uses the current branch's PR. For CI that ran and failed, use /ship-pr."
capability: "Merge a pull request whose CI passed on its head commit, or on local CI evidence when GitHub Actions cannot start (for all runs or only some), never triggered for the head commit, or the repository has no CI, within fixed limits."
side_effect_level: remote_write
approval_required: true
requires_tools: "git and gh; the commands in the repository's workflow files, or its declared build, lint and test commands when it has none."
output_schema: "Which case held (the green run ids; the passed run ids plus the not-started annotation for a mixed result; or why remote CI could not run, with run ids and the annotation; or that no run registered for the head commit, with the repository's last run; or that the head commit has no workflows and no runs), a table of each local workflow step with its exit code when one ran, the merge commit, and anything left with the reason and a paste-ready command."
risk_class: high
disable-model-invocation: true
---

# Merge PR

`/merge-pr` means: **merge this PR.** When its CI already passed on the head commit, that is the
evidence. When GitHub produced no CI result for it (its Actions can't start, no run ever registered,
or the repository has none), the evidence is a local run. When only some runs started and passed, they count, and only the rest are
replayed locally. Typing it approves merging this PR and nothing else. It is not
standing approval, and it never pushes fixes. Never run this skill on your own initiative.

One PR per run. If the user names none, use the current branch's PR. If that's ambiguous, stop and ask.

How this differs from `/ship-pr`: `/ship-pr` works from CI results. It fixes CI failures and merges once
CI is green.
`/merge-pr` doesn't need CI and never fixes anything. It merges when CI is already green, and when
GitHub gave no CI result at all: no job could start, no run ever registered, or the repository has no
CI. Then a local run on the head commit is the evidence. When the user typed `/merge-pr`, handle those
cases here; don't send them to `/ship-pr`. A job that started and failed is a real failure: stop and
point to `/ship-pr`.

## 1. Confirm the target

Read `gh pr view <n> --json state,author,baseRefName,headRefName,headRefOid,isDraft,mergeable,mergeStateStatus,reviewDecision,body`
and `gh repo view --json visibility,nameWithOwner`.

- Already merged: report it and stop.
- Stop and report if it isn't the user's PR, is a draft, has changes requested, conflicts with its
  base, or another session is working on its branch (`ListAgents`). A PR based on another open PR waits
  for that one.
- **Stop on `mergeStateStatus` `BLOCKED`.** Branch protection is holding the merge (a required check,
  review or rule). Read the required checks from it with `gh api repos/<owner>/<repo>/branches/<base>/protection`
  where the token allows; they are the "required" checks in step 3.
- **Review sign-off still applies.** If the project tracks work (an `.agent-flow/` folder) and the PR
  body says `Refs <ticket>`, that ticket must be approved (`done`) by a reviewer other than its author.
  If it's still in review, stop; this skill never stands in for a review.
- Record the head commit `<sha>`. Every later step is about that commit.

## 2. Find out which case holds

List the runs for the head commit: `gh run list --commit <sha> --json databaseId,name,status,conclusion`.
`gh pr checks` often returns HTTP 403 with this token; for Actions, the runs API is the source. Then
list the workflows on that commit: `git ls-tree -r --name-only <sha> -- .github/workflows`.

**Read the checks outside Actions in every case.** `gh api repos/<owner>/<repo>/commits/<sha>/check-runs`
and `gh api repos/<owner>/<repo>/commits/<sha>/status` list third-party check runs and commit statuses
that `gh run list` can't see. Any failing or pending entry that isn't one of the Actions jobs listed
above stops the run. If those APIs return 403, say in the report that checks outside Actions could not
be seen, and stop if branch protection or recent base commits show that such checks exist.

**Wait for runs to register.** After a push in the last five minutes, wait that long before deciding
any case: a workflow that hasn't queued yet is invisible, and the commit would read as green or as
having no CI.

Exactly one of these five cases must hold.

**CI already passed.** This case holds only when **all** of these are true:

- at least one run exists for `<sha>`, every run is `completed`, and every run's conclusion is
  `success` (`skipped` and `neutral` count as passing, but only next to at least one `success`: runs
  that were all skipped don't count as passed);
- no check from outside Actions failed: the check-runs and status APIs for `<sha>` (above) show no
  failing or pending entry;
- `mergeStateStatus` is not `BLOCKED`.

Quote the green run ids in the report, skip step 3, and go to step 4. A run on an older commit doesn't
count: the runs must be for `<sha>`.

**Actions could not start.** This case holds only when **all** of these are true:

- the head commit has `.github/workflows`;
- at least one run exists for `<sha>`, and every run is `completed`. Pending or queued runs mean wait,
  then stop if they are still pending after about 15 minutes;
- for every run, no job executed a step: `gh run view <id> --json jobs` shows jobs with no steps, or
  `gh run view <id>` shows an annotation that the job was not started, such as "recent account payments
  have failed or your spending limit needs to be increased", "spending limit", or "You have exceeded
  the included minutes";
- the same cause failed a run on another recent commit, one outside this PR's branch (the base branch
  or another PR), so it isn't specific to this change;
- no check outside Actions failed or is pending (above).

**Do the one infrastructure rerun first** (`gh run rerun <id>`), and never more than one. If its jobs
still don't start, this case holds. If a job now runs a step, decide again on the rerun's result: all
green is the "CI already passed" case; a job that ran and failed means stop, a real failure for
`/ship-pr`.

Quote the annotation and the run ids in the report. If any job ran a step and failed, stop: that is a
real failure for `/ship-pr`.

**CI never triggered.** Workflows exist, but GitHub never registered a run for this commit. This case
holds only when **all** of these are true:

- the head commit or the base branch's tip has `.github/workflows`;
- no run exists for `<sha>` at least 15 minutes after the head was pushed, well past the registration
  wait above. The push time is the branch's latest push in
  `gh api "repos/<owner>/<repo>/activity?ref=refs/heads/<headRefName>&per_page=1" --jq '.[0].timestamp'`,
  not the commit date;
- the silence isn't specific to this PR: at least one other commit pushed outside this PR's branch since
  the repository's last run (the base branch or another PR) also has no run. A PR can't switch its own
  CI off;
- no check from outside Actions exists or is pending for `<sha>` (above);
- `mergeStateStatus` is not `BLOCKED`.

Record why, as far as GitHub shows it, and quote it in the report: the repository's last run of any
kind (`gh run list --limit 1 --json createdAt,event,headBranch`), the workflow's state
(`gh api repos/<owner>/<repo>/actions/workflows`), whether Actions is enabled
(`gh api repos/<owner>/<repo>/actions/permissions`), and whether the workflow's `on:` filters
(branches, paths, types) match this PR. No cause is needed beyond that evidence and the check that
other commits are silent too. Don't push,
close and reopen the PR, or dispatch a workflow to get a run: that changes the PR or starts work the
user didn't ask for. If a run appears while you check, decide again from the top of this step.

Then replay the workflows in step 3. If the PR deletes its workflows, replay the base branch's. If the
diff touches `.github/workflows` at all, replay the base branch's workflows as well as the head's, so
an edited trigger or step can't decide what gets checked.

**The repository has no CI.** This case holds only when **all** of these are true:

- `git ls-tree` lists nothing under `.github/workflows` for `<sha>`, and nothing for the base branch's
  tip (`git fetch origin <base>` first, so the tip is current, then
  `git ls-tree -r --name-only origin/<base> -- .github/workflows`). A PR that deletes the workflows
  doesn't make the repository CI-free: that is "CI never triggered", with the base branch's workflows
  replayed;
- no run exists for `<sha>`;
- no check from outside Actions exists either: `gh api repos/<owner>/<repo>/commits/<sha>/check-runs`
  lists no check runs and `gh api repos/<owner>/<repo>/commits/<sha>/status` lists no statuses, and
  the base branch's latest few commits have none either. If that API returns 403, say in the report
  that checks outside Actions could not be seen.

They must hold for the base branch as well as for the head commit. Quote these results in the report in
place of the annotation.

**Some runs passed, the rest could not start.** This case holds only when **all** of these are true:

- every run for `<sha>` is `completed`;
- each run either passed (as in "CI already passed", with at least one `success`) or had no job execute
  a step, with a not-started annotation (as in "Actions could not start");
- at least one run did not start (otherwise this is "CI already passed");
- the same not-started cause failed a run on another recent commit outside this PR's branch;
- the one infrastructure rerun of the not-started runs was done first, as above, and they still didn't
  start;
- no check outside Actions failed or is pending, and `mergeStateStatus` is not `BLOCKED`.

The passed runs count as evidence: replay only the workflows whose jobs didn't start, in step 3. Quote
the passed run ids and the not-started annotation in the report.

Anything else means stop and report: no run registered yet within 15 minutes of the push, runs are
still pending after the wait above, every run was skipped, or a job ran a step and failed.

## 3. Run CI locally on the exact commit

Ignored files make a shared checkout lie (agent folders, caches, local config), so use a fresh,
detached worktree:

```bash
git fetch origin <headRefName>
git worktree add --detach <scratch>/merge-pr-<n> <sha>
```

**With workflows,** read every workflow that triggers on `pull_request` or `push` to the base branch.
Run each job's `run:` steps in order, with the same commands, working directory and environment values,
from the worktree. In the "some runs passed" case, replay only the workflows whose jobs didn't start;
the passed runs already cover the rest. If no workflow triggers on `pull_request` or a push to the base
branch, there is nothing to replay: stop and report. An empty table isn't evidence for a merge.

**With no CI,** there is no workflow to replay. Run the project's declared checks instead: the build,
lint and test commands in its `AGENTS.md`, `CLAUDE.md` or README, then the standard checks of each
toolchain the diff touches (for example `cargo fmt --check`, `cargo clippy` and `cargo test` for a
Cargo workspace). If no check covers the changed files, stop and report: a diff review alone isn't
evidence for a merge.

In both cases:

- **Never pipe or chain a check into anything that hides its exit code** (`| tail`, `; echo`). Record
  each step's exit code.
- Matrix jobs: run the entry that matches this host. List the other entries as not verified.
- `uses:` steps that only set up a toolchain (checkout, setup-python, setup-node) are covered by the
  local toolchain; say which version you used. Any other `uses:` step, or a step that needs secrets
  or a service you don't have, is not covered: list it. If a **required** check can't be reproduced
  at all, stop and report. Don't merge on partial evidence.
- Also run the project's declared test command if the workflow doesn't, plus any test suite the
  project's notes say CI misses.

Then review the PR in place of a reviewer's CI glance:

- the diff (`git diff <base>...<sha> --stat`) holds only the files the PR is meant to change;
- the added lines have no machine paths, identities or credentials.

Any failing step: stop and report it with its output. Don't fix it here; that's `/ship-pr` or new work.

## 4. Merge

Immediately before merging, re-read the PR and confirm:

- the head is still `<sha>`, with no new commits;
- it is mergeable with no conflicts, `mergeStateStatus` is not `BLOCKED`, and no review has changed;
- the checks outside Actions still show nothing failing or pending;
- the runs for `<sha>` still show the case from step 2: all green, only the not-started cause, the same
  mix of passed and not-started runs, or, when CI never triggered or there is none, still none.

Use the merge method the repository's recent PRs used, pinned to the checked commit:

```bash
gh pr merge <n> --merge --delete-branch --match-head-commit <sha>
```

Run it from a clean checkout. `gh` switches the local branch after merging, and a modified tracked
file (for example an `.agent-flow/tickets.jsonl` snapshot) makes that local step fail after the remote
merge succeeded. If it fails, check `gh pr view <n> --json state,mergeCommit` before retrying anything.

## 5. Verify and clean up

- Confirm the PR shows as merged and record the merge commit. With green CI, the base branch's run on
  the merge commit is the usual follow-up. Otherwise note that the base branch's CI will also be
  blocked, or that there is none; say so rather than waiting for it.
- Return a shared checkout to its default branch, and fast-forward it only if it's clean.
- Remove the worktree this run created with `git worktree remove <path>`, but only if no step created
  links inside it (`node_modules` from a package install, junctions). Otherwise leave it and give the
  user the steps: remove the links first, then the worktree. This differs from `/ship-pr`, which leaves
  every worktree for the user, on purpose: `/merge-pr` made this one itself, fresh, and ran every step
  in it, so it knows whether any links exist.

## Report

With green CI, the first line reads: `**PR #<n>** merged as <merge sha>. CI passed on <sha> (runs <ids>).`
No table is needed.

Otherwise:

```markdown
**PR #<n>** merged as <merge sha> on local evidence. GitHub CI did not start: "<annotation>" (runs <ids>).

| Workflow step | Command | Exit |
|---|---|---|
| ci / lint | `python scripts/check_x.py` | 0 |

Not covered: <steps, or "none">
```

With some runs passed and the rest not started, the first line reads: `**PR #<n>** merged as <merge sha>.
CI passed on <sha> (runs <ids>); the rest did not start: "<annotation>" (runs <ids>).` The table lists
only the replayed workflows' steps.

When CI never triggered, the first line reads: `**PR #<n>** merged as <merge sha> on local evidence.
GitHub registered no CI run for <sha>; the repository's last run was <date>.` The table lists the
replayed workflow steps.

With no CI, the first line reads: `**PR #<n>** merged as <merge sha> on local evidence. The repository
has no CI: no workflows and no runs on <sha>.` The table lists the declared checks you ran.

Say what CI would have covered that the local run didn't (other platforms, matrix entries, secrets),
and name what would make CI run again (for example, raising the Actions spending limit, or checking
why the workflow stopped triggering) or, with no CI, that there is none to run.

## Never

Leave these for the user, with a paste-ready command where one helps:

- Merging when any CI job actually ran and failed, or while runs are still pending.
- Merging past a review that isn't approved, or with admin rights to get past branch protection.
- Pushing commits to the PR, force-pushing, or editing workflows or required checks.
- Weakening a check: skipping tests, loosening assertions, raising timeouts.
- Editing permission policy, tagging, releasing or deploying.
- Merging any PR other than the one named.

## When to stop

Stop and report when a hook or deny rule blocks a command (**never reword a command to get past a
block**), none of the cases in step 2 can be shown, a required step can't be reproduced locally, a local
step fails, or the PR's state changes under you. Stopping is a good result.
