---
name: decide-with-agents
description: Use when a decision, a research question or a plan approval should be settled by investigation rather than by asking the user, e.g. "run a sub-agent researcher to decide", "review by fable sub-agent to decide", "research the open questions", "approve the plan", "run reviewers then use jev", or when an open choice needs evidence before Jev can call it. Runs independent sub-agents (model chosen by task complexity), checks what they claim, then lets Jev make the final call in one batched request and records a receipt.
capability: "Settle decisions, research questions and plan approvals: brief sub-agents by complexity (Fable/Opus/Sonnet), verify their findings, resolve with one Jev call, act or hand owner-only items back, record provenance."
side_effect_level: remote_write
approval_required: false
requires_tools: "Agent tool (sub-agents with a model override); MCP jev-rw-systemone (jev_system_one) or jev-engineering."
output_schema: "Per decision: investigation summary with evidence, Jev answer and confidence, action taken or item handed back, receipt path."
risk_class: medium
---

# Decide with agents

Investigate first, then let Jev call it. The sub-agents gather and check evidence. Jev picks from a closed set of
options. You act only on what is reversible and allowed, and you record where the decision came from.
`use-jev` owns the Jev thresholds and hard limits. This skill adds the investigation in front of the Jev call and
the checks after it.

## 1. Frame each decision

For every open item, write:
- the question, in neutral words;
- the closed options, plus "defer / none fits";
- what an answer must rest on: files, numbers, a test, a measurement.

Settle by a deterministic check instead whenever one answers the question: a file says so, a hash, a count, a
test, a pool size. A Jev call is for judgment, not for facts.

Owner-only items stay with the owner unless the owner delegated them. Those are policy, scope, thresholds in a
frozen artifact, licences, spending, deletes and merges to the default branch. Delegated items are recorded as
delegated (step 6).

## 2. Pick the sub-agent model by task complexity

| Task | Model | Examples |
|---|---|---|
| A policy or methodology decision, a review against acceptance criteria, approving a plan, or weighing trade-offs | **Fable** | Which counting rule; whether a floor belongs in a frozen config; approve or reject a ticket |
| Multi-file investigation, analysis over data, or a code-path trace across modules | **Opus** | Is a path safe across every removal route; recompute counts from raw records |
| A narrow fact: one file, one lookup, a public licence or model card | **Sonnet** | Does this checkpoint exist; what does this function return |

- Use one agent per independent question. Batch questions into one agent when they share the same evidence.
- Pass the model with the Agent tool's `model` override.
- For acceptance reviews in agent-flow projects, use `agent-flow:flow-reviewer`.
- Run agents in the background when other work can proceed. Never predict their results.

## 3. Brief the agent

Use [`references/brief-template.md`](references/brief-template.md). Every brief fixes:
- read-only scope;
- a scratch folder for anything it writes;
- no GPU or network unless the brief allows it;
- the report as its final message, not a file (the harness refuses report files written by sub-agents), with a
  word cap;
- the project's prohibited terms;
- for reviewers, a detached worktree instead of switching the shared checkout.

Ask for file:line or numbers behind every claim, and for an explicit "owner-only vs delegable" line.

## 4. Check what came back

Agents make confident mistakes. Before relaying a finding:
- spot-check the claims the decision rests on: re-run one count, open the cited line;
- treat a finding that contradicts your own earlier report as a correction: fix the report and say so;
- ask a follow-up about a finding by resuming the same agent: `SendMessage` to its ID (a name may not survive a
  restart). It keeps its full history and reports back to you. Spawn a fresh agent only for an independent question;
- file discovered work as tickets in agent-flow projects, not as notes in chat.

## 5. Let Jev make the final call

Use one `jev_system_one` batch over the verified findings. Choice questions need a `criteria` object.
- **State:** the numbers, reversibility, who owns the item and the researcher's recommendation.
- **Options:** every option the investigation left standing, plus "defer".
- **Thresholds:** act and re-ask as in `use-jev` (act at confidence ≥ 0.5 on a reversible pick; re-ask once
  when it is low).

Then check that the pick can actually be carried out, with a deterministic check: the pool exists, the option is
reachable, the tool is installed. If a fact changed, or a Jev score contradicts the pick (a high choice with a low
soundness Noul), re-ask **once** with the new fact. Never act on an infeasible pick.

## 6. Act and record

- **Do:** reversible, allowed picks, through the normal workflow (branch, tests, PR).
- **Hand back:** owner-only actions. Use one clickable question, with Jev's pick as the recommended option.
- **Write a receipt beside the evidence** (for example `jev-decision-<topic>.json`): the question, the options,
  model, choice, probabilities, the research it rested on, and
  `approved_by: "owner, delegated to Jev (jev-1.14.0 <choice> p=<p>)"`.
  Add a decision-register row or a ticket note when the project keeps one.
- **Report:** one line per decision: choice (p), action, receipt path.

## Do not

- Ask Jev a factual question that a file, a count or a test answers.
- Relay a sub-agent's claim you did not check when the decision depends on it.
- Let a sub-agent edit, commit, push, merge or switch the shared checkout.
- Treat Jev's pick or a skill invocation as consent for a removal, a merge to the default branch or a licence.

## Related

- `use-jev`: thresholds, hard limits and provenance wording.
- `flow-review`, `agent-flow:flow-reviewer`: acceptance reviews in agent-flow projects.
- `subagent-review`: external Codex, Gemini or swarm judges.
