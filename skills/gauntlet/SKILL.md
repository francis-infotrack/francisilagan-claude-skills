---
name: gauntlet
description: Run a feature through the Uncle Bob agent gauntlet at a chosen weight — two-pack (coder ↔ finisher tight loop), four-pack (spec-driven without separate hardening/QA agents), or the full six-pack (specifier → coder → cleaner → architect → hardener → QA) — with deterministic quality gates (CRAP ≤ 6, architecture checks, mutation testing) and, for the six-pack, an executable QA run plus evidence report. Use when a story should come out mutation-hardened; pick the pack by stakes and size.
argument-hint: [2|4|6] [issue ref | feature description | spec file path]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent
---

Run **$ARGUMENTS** through the agent gauntlet. If the first token of the arguments is `2`, `4`, or `6`, that selects the pack; otherwise default to **6**. If the remaining argument is an issue reference (`#42`, `owner/repo#42`, or an issue URL) the run is in **ticket mode** — see that section; it changes claiming, pack choice, pushing, and completion. Everything else is unchanged. You are the orchestrator: you dispatch the stage agents, carry their reports forward, and enforce the handoff rules. You do not write production code yourself.

The six agent files at `~/.claude/agents/gauntlet-*.md` are the single source of truth for each responsibility. Smaller packs don't get watered-down copies — they get **composed roles**: one dispatch whose prompt tells the agent to execute several role files in order within one context. When composing, instruct the agent to read the named role files and apply them; pass the slug, branch, and prior stage report as usual.

## Picking a pack

- **Two-pack** — tight implement/refine loop. Small, well-understood changes where a written spec would restate the request. No Gherkin, no QA stage.
- **Four-pack** — disciplined spec-driven work without separate cleanup/architecture/hardening/QA contexts. Medium stories where the spec matters but end-to-end QA automation isn't warranted.
- **Six-pack** — the full gauntlet with independent QA and an evidence report. Major or risky stories; each quality gate owned by a fresh context.

## Setup (all packs)

1. Read the project's CLAUDE.md (or equivalent) for its test/build commands, branch conventions, and any local constraints — the stage agents will need these passed along.
2. `git fetch origin`; confirm the branch isn't behind the default branch. New work gets a fresh branch off the latest default branch.
3. Derive a short stable slug (e.g. `csv-export`). Stage artifacts live in `.claude/specs/gauntlet/<slug>/` (keep it out of version control; create it if needed).
4. Restore/verify the project's coverage and mutation tooling if it has a tool manifest.

## Two-pack: coder ↔ finisher

1. **gauntlet-coder** — pass the raw behaviour request (two-pack mode: no spec file; unit-test-encoded behaviours). Gate: impacted suites green, committed.
2. **Finisher** (composed) — dispatch `gauntlet-cleaner` with this addition: *"After the CRAP loop and review pass, in this same pass apply the review phases and deterministic gate of `~/.claude/agents/gauntlet-architect.md`, then the mutation work of `~/.claude/agents/gauntlet-hardener.md` (differential, touched files only). Read both files and follow them. Report per role."* Gate: CRAP ≤ 6, architecture checks green, zero surviving non-equivalent mutants.
3. If the request has multiple behaviour slices, loop 1 → 2 per slice rather than batching everything into one giant diff.

## Four-pack: specifier → coder → refactorer → architect

1. **gauntlet-specifier** — four-pack mode: Gherkin only, no QA procedure.
2. **gauntlet-coder** — standard.
3. **Refactorer** (composed) — dispatch `gauntlet-cleaner` with this addition: *"You also own property-test assessment in this pack: identify invariants in the touched domain logic (round-trips, conservation, idempotence, ordering) and propose concrete property-test cases in your report — do not add packages unilaterally."* Gate: CRAP ≤ 6, suites green.
4. **Hardening architect** (composed) — dispatch `gauntlet-architect` with this addition: *"After the structural review and its gate, in this same pass execute the mutation work of `~/.claude/agents/gauntlet-hardener.md` (differential, touched files only, tests-only additions). Read that file and follow it."* Gate: architecture checks green, zero surviving non-equivalent mutants.

## Six-pack: the full gauntlet

Sequential, one stage per fresh context:

1. **gauntlet-specifier** → `acceptance.feature` + `qa-procedure.md`. Present spec summary and assumptions to the user if present; in an autonomous run, proceed and record assumptions in the final report.
2. **gauntlet-coder** → implementation + tests. Gate: impacted suites green.
3. **gauntlet-cleaner** → refactored diff. Gate: CRAP ≤ 6, suites green.
4. **gauntlet-architect** → boundary review. Gate: architecture checks green; new checks committed where a boundary was worth locking.
5. **gauntlet-hardener** → added tests. Gate: zero surviving non-equivalent mutants; no leftover mutations in the tree.
6. **gauntlet-qa** → executable QA script + `evidence.md`. Gate: every QA step PASS.

## Handoff rules (all packs)

- A stage that fails its gate loops **within itself** until the gate passes — the gate's verdict is the exit condition, not the agent's judgment.
- A stage that discovers an upstream defect (spec contradiction, production bug, dead branch) does not fix it in place. Bounce: re-dispatch the owning upstream stage with the finding, then re-run the stages between. After the second bounce for the same finding, stop and surface it to the user.
- Every stage commits its own work in the project's commit convention before handoff. Never squash stages together — per-stage commits are the audit trail.
- Respect the machine: stages run one at a time, narrow test scopes, `nice -19` for mutation runs.

## Ticket mode (issue reference given)

Ticket mode is how you hand a GitHub issue to the gauntlet. It makes the run visible on the Personal Engineering board through the repo's `project-sync` workflow, so it is the one mode that pushes and opens a PR. `gh-board` (on PATH) is the board client; never write to the board any other way.

1. **Read the ticket**: `gh issue view <ref> --comments`. The body plus comments (triage brief included) is the feature description you hand to the specifier, or to the coder in a two-pack.
2. **Pick the pack** if no pack token was given: `gh-board field <ref> Effort` → `XS` or `S` = two-pack, `M` = four-pack, `L` or `XL` = six-pack, unset = six-pack.
3. **Claim before any work**: `gh issue edit <ref> --add-assignee @me`, then `gh-board status <ref> "In Progress"`, then comment on the issue: `> *Gauntlet started (pack N) on branch gauntlet/<slug>.*` The assignee is the claim: never start work on an issue that already has an assignee.
4. **Branch**: if the current branch already starts with `gauntlet/` (an existing worktree for this ticket), use it and take the slug from the branch name. Otherwise create `gauntlet/<number>-<kebab-title>` off `origin/<default branch>`.
5. **Draft PR after the first committing stage** (the coder): `git push -u origin HEAD`, then `gh pr create --draft` with a title in the repo's commit convention and a body of `Closes #<number>` followed by the pack and stage list. `project-sync` moves the card on that event. Every later stage commits locally and does **not** push: each push re-runs CI on the PR, and the minutes are billed. Local commits survive an interrupted session, so commit often; push only at completion or when blocked.
6. **Completion**: `git push`, then `gh pr ready <pr>` (the card moves to In Review), then comment the per-stage results on the PR; for a six-pack paste `evidence.md`.
7. **Blocked** (second bounce on the same finding, or a gate that cannot pass): `git push` so the draft shows the work, comment the blocker on the PR and on the issue, `gh issue edit <ref> --add-label needs-human` (create it with `gh label create needs-human --color B60205` if the repo lacks it), leave the PR as a draft, and stop. Do not move the card; the supervisor pass flags the stale draft.

## Completion

Report per-stage results and the commit list (six-pack: summarise `evidence.md`). In ticket mode the PR is already open and marked ready; in every other mode stop at the branch — do not push or open a PR unless the user asked. Hand off to the project's merge/ship flow from there.
