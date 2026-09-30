---
name: gauntlet
description: Run a feature through the Uncle Bob agent gauntlet at a chosen weight — two-pack (coder ↔ finisher tight loop), four-pack (spec-driven without separate hardening/QA agents), or the full six-pack (specifier → coder → cleaner → architect → hardener → QA) — with deterministic quality gates (CRAP ≤ 6, architecture checks, mutation testing) and, for the six-pack, an executable QA run plus evidence report. Use when a story should come out mutation-hardened; pick the pack by stakes and size.
argument-hint: [2|4|6] [--no-gate] [--restart] [--model <alias>] [issue ref | feature description | spec file path]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, AskUserQuestion
---

Run **$ARGUMENTS** through the agent gauntlet. If the first token of the arguments is `2`, `4`, or `6`, that selects the pack; otherwise default to **6**. A `--no-gate` token anywhere skips the interactive spec gate; `--restart` ignores any saved run state (see Resume); `--model <alias>` (e.g. `opus`, `sonnet`) runs every stage on that model. If the remaining argument is an issue reference (`#42`, `owner/repo#42`, or an issue URL) the run is in **ticket mode** — see that section; it changes claiming, pack choice, pushing, and completion. Everything else is unchanged. You are the orchestrator: you dispatch the stage agents, carry their reports forward, and enforce the handoff rules. You do not write production code yourself.

The six agent files at `${CLAUDE_PLUGIN_ROOT}/agents/gauntlet-*.md` are the single source of truth for each responsibility. They ship in this plugin, so dispatch them with `subagent_type` `francis:gauntlet-<stage>` (e.g. `francis:gauntlet-coder`); the names below omit the prefix. Smaller packs don't get watered-down copies — they get **composed roles**: one dispatch whose prompt tells the agent to execute several role files in order within one context. When composing, instruct the agent to read the named role files and apply them; pass the slug, branch, and prior stage report as usual.

**Models.** Each agent file pins its model: `opus` for specifier, architect, hardener — the strong model where a mistake propagates downstream (spec, boundaries, equivalent-mutant judgement); `sonnet` for coder, cleaner, QA — the fast model for volume work (swarm-forge's careful-backend split). A composed role runs on the model of the agent file dispatched, so dispatch the two-pack **Finisher** with the Agent tool's `model: opus` override (it absorbs architect + hardener judgement); the four-pack Hardening architect is already opus. `--model <alias>` overrides every dispatch.

## Picking a pack

- **Two-pack** — tight implement/refine loop. Small, well-understood changes where a written spec would restate the request. No Gherkin, no QA stage.
- **Four-pack** — disciplined spec-driven work without separate cleanup/architecture/hardening/QA contexts. Medium stories where the spec matters but end-to-end QA automation isn't warranted.
- **Six-pack** — the full gauntlet with independent QA and an evidence report. Major or risky stories; each quality gate owned by a fresh context.

## Setup (all packs)

1. Read the project's CLAUDE.md (or equivalent) for its test/build commands, branch conventions, and any local constraints — the stage agents will need these passed along.
2. `git fetch origin`; confirm the branch isn't behind the default branch. New work gets a fresh branch off the latest default branch.
3. Derive a short stable slug (e.g. `csv-export`). Stage artifacts live in `.claude/specs/gauntlet/<slug>/` (keep it out of version control; create it if needed).
4. Restore/verify the project's coverage and mutation tooling if it has a tool manifest. The CRAP gate needs Cobertura XML from the project's own coverage command (its CLAUDE.md stage table) and `crap-gate` (on PATH via the plugin); pass the default branch to every stage so they run `crap-gate --since origin/<default>`.
5. Check for saved run state (see Resume) before dispatching anything.

## Two-pack: coder ↔ finisher

1. **gauntlet-coder** — pass the raw behaviour request (two-pack mode: no spec file; unit-test-encoded behaviours). Gate: impacted suites green, committed.
2. **Finisher** (composed) — dispatch `gauntlet-cleaner` with this addition: *"After the CRAP loop and review pass, in this same pass apply the review phases and deterministic gate of `${CLAUDE_PLUGIN_ROOT}/agents/gauntlet-architect.md`, then the mutation work of `${CLAUDE_PLUGIN_ROOT}/agents/gauntlet-hardener.md` (differential, touched files only). Read both files and follow them. Report per role."* Dispatch with `model: opus`. Gate: `crap-gate` exits 0, architecture checks green, zero surviving non-equivalent mutants.
3. If the request has multiple behaviour slices, loop 1 → 2 per slice rather than batching everything into one giant diff.

## Four-pack: specifier → coder → refactorer → architect

1. **gauntlet-specifier** — four-pack mode: Gherkin only, no QA procedure. Then the **spec gate**.
2. **gauntlet-coder** — standard.
3. **Refactorer** (composed) — dispatch `gauntlet-cleaner` with this addition: *"You also own property-test assessment in this pack: identify invariants in the touched domain logic (round-trips, conservation, idempotence, ordering) and propose concrete property-test cases in your report — do not add packages unilaterally."* Gate: `crap-gate` exits 0, suites green.
4. **Hardening architect** (composed) — dispatch `gauntlet-architect` with this addition: *"After the structural review and its gate, in this same pass execute the mutation work of `${CLAUDE_PLUGIN_ROOT}/agents/gauntlet-hardener.md` (differential, touched files only, tests-only additions). Read that file and follow it."* Gate: architecture checks green, zero surviving non-equivalent mutants.

## Six-pack: the full gauntlet

Sequential, one stage per fresh context:

1. **gauntlet-specifier** → `acceptance.feature` + `qa-procedure.md`. Then the **spec gate**.
2. **gauntlet-coder** → implementation + tests. Gate: impacted suites green.
3. **gauntlet-cleaner** → refactored diff. Gate: `crap-gate` exits 0, suites green.
4. **gauntlet-architect** → boundary review. Gate: architecture checks green; new checks committed where a boundary was worth locking.
5. **gauntlet-hardener** → added tests. Gate: zero surviving non-equivalent mutants; no leftover mutations in the tree.
6. **gauntlet-qa** → executable QA script + `evidence.md`. Gate: every QA step PASS.

## Spec gate (four- and six-pack)

Humans own the spec; agents own everything after it. No coder dispatch until the gate passes.

- **Interactive run** (not ticket mode, no `--no-gate`): show the user the scenario list (ID + title), every assumption with its tag, and — six-pack — a one-line-per-step summary of `qa-procedure.md`, with the spec paths. Ask with AskUserQuestion: **Approve** / **Revise** (the user's notes go back to a fresh `gauntlet-specifier` dispatch in revision mode, then the gate runs again) / **Stop**. Record the approval, and any notes, in the final report.
- **Ticket mode**: the issue reaching Ready was the human gate. Proceed unless the specifier recorded any **[behavioural]** assumption — then comment the scenario list and those assumptions on the issue as questions, `gh issue edit <ref> --add-label needs-human --remove-assignee @me`, `gh-board status <ref> "Backlog"`, and stop. No branch push, no PR. Whoever answers removes the label and moves the card back to Ready.
- **`--no-gate`**: proceed, and list every assumption in the final report.

## Handoff rules (all packs)

- A stage that fails its gate loops **within itself** until the gate passes — the gate's verdict is the exit condition, not the agent's judgment. For CRAP that verdict is `crap-gate`'s exit code: 0 pass, 1 fail, 2 BLOCKED (surface its message; nobody eyeballs scores). Exemptions (flat switch, thin shell) only as `--allow path:function`, listed in the report.
- Hardener and QA are tests-only: a plugin hook blocks their Edit/Write to non-test paths. A block is a bounce upstream, never something to route around with Bash (repos with unusual test layouts list globs in `.claude/gauntlet-test-paths`).
- A stage that discovers an upstream defect (spec contradiction, production bug, dead branch) does not fix it in place. Bounce: re-dispatch the owning upstream stage with the finding, then re-run the stages between. After the second bounce for the same finding, stop and surface it to the user.
- Every stage report ends with its requirement → evidence table (composed dispatches: one per role). A report without one, or with an unexplained GAP, goes back to the same stage.
- Every stage commits its own work in the project's commit convention before handoff. Never squash stages together — per-stage commits are the audit trail.
- Respect the machine: stages run one at a time, narrow test scopes, `nice -19` for mutation runs.

## Resume and run state (all packs)

Maintain `.claude/specs/gauntlet/<slug>/state.json`:

```json
{"pack": 6, "slug": "...", "branch": "...", "stage_index": 0,
 "stages": [{"name": "coder", "model": "sonnet", "status": "passed|failed|bounced|pending",
             "commit": "<sha>", "gate_output_summary": "...", "started": "<date -Is>",
             "finished": "<date -Is>", "bounces": 0, "headline": {}}],
 "spec_gate": "approved|pending|skipped", "bounces": {"<finding>": 1}}
```

- Write it after every gate verdict (and each bounce). Stamp `started`/`finished` with `date -Is`. `headline` holds the stage's numbers from its report: CRAP failures fixed, mutants generated/killed/equivalent, QA steps pass/fail. Composed roles are one entry each (`finisher`, `refactorer`, `hardening-architect`).
- **On start**: if `state.json` exists for the slug and its branch is the current branch, verify the last passed stage's `commit` is on the branch (`git merge-base --is-ancestor <commit> HEAD`). If it is, tell the user you are resuming and continue at the first non-passed stage; if not, start over. `--restart` ignores the file and starts over.

## Ticket mode (issue reference given)

Ticket mode is how you hand a GitHub issue to the gauntlet. It makes the run visible on the Personal Engineering board through the repo's `project-sync` workflow, so it is the one mode that pushes and opens a PR. `gh-board` (on PATH) is the board client; never write to the board any other way.

1. **Read the ticket**: `gh issue view <ref> --comments`. The body plus comments (triage brief included) is the feature description you hand to the specifier, or to the coder in a two-pack.
2. **Pick the pack** if no pack token was given: `gh-board field <ref> Effort` → `XS` or `S` = two-pack, `M` = four-pack, `L` or `XL` = six-pack, unset = six-pack.
3. **Claim before any work**: `gh issue edit <ref> --add-assignee @me`, then `gh-board status <ref> "In Progress"`, then comment on the issue: `> *Gauntlet started (pack N) on branch gauntlet/<slug>.*` The assignee is the claim: never start work on an issue that already has an assignee — except a resume, where the assignee is you and `state.json` matches; skip the claim then.
4. **Branch**: if the current branch already starts with `gauntlet/` (an existing worktree for this ticket), use it and take the slug from the branch name. Otherwise create `gauntlet/<number>-<kebab-title>` off `origin/<default branch>`.
5. **Draft PR after the first committing stage** (the coder): `git push -u origin HEAD`, then `gh pr create --draft` with a title in the repo's commit convention and a body of `Closes #<number>` followed by the pack and stage list. `project-sync` moves the card on that event. Every later stage commits locally and does **not** push: each push re-runs CI on the PR, and the minutes are billed. Local commits survive an interrupted session, so commit often; push only at completion or when blocked.
6. **Completion**: `git push`, then `gh pr ready <pr>` (the card moves to In Review), then comment the per-stage results on the PR; for a six-pack paste `evidence.md`.
7. **Blocked** (second bounce on the same finding, or a gate that cannot pass): `git push` so the draft shows the work, comment the blocker on the PR and on the issue, `gh issue edit <ref> --add-label needs-human` (create it with `gh label create needs-human --color B60205` if the repo lacks it), leave the PR as a draft, and stop. Do not move the card; the supervisor pass flags the stale draft.

## Completion

Report per-stage results and the commit list (six-pack: summarise `evidence.md`, which carries the Run cost table). Two- and four-pack: print a **Run cost** table from `state.json` — stage, model, wall time, bounces, headline numbers. No token or cost figures; wall time + model is the proxy. In ticket mode the PR is already open and marked ready; in every other mode stop at the branch — do not push or open a PR unless the user asked. Hand off to the project's merge/ship flow from there.
