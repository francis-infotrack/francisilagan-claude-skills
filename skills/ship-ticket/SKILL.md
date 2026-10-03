---
name: ship-ticket
description: Take a GitHub issue from Ready to merged with no human in the loop — claim it, implement it through the gauntlet (ticket mode, draft PR), then loop a fresh code review (built-in `code-review` plus an acceptance-criteria check) and a fresh fixer sub-agent until a review round produces no fixes or only Low-severity findings, wait for CI, and squash-merge. Use when the user says "ship ticket", "pick up a ticket and implement it end to end", or "/ship-ticket".
argument-hint: "[#issue | issue URL] [2|4|6]  (no issue = top Ready item on the board)"
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, Skill
---

Ship **$ARGUMENTS** end to end. You are the orchestrator: you pick the ticket, run the
gauntlet, drive the review ↔ fix loop, and merge (no approval). You never edit production code or tests
yourself — sub-agents do that. The user has authorised this skill to push, open the PR,
and merge without asking; that authorisation covers only the PR this run creates.

Read the repo's CLAUDE.md / AGENTS.md first: its test commands, byte-pin rules and commit
convention go into every sub-agent prompt verbatim.

## 1. Pick the ticket

- Issue given → use it.
- No issue → `gh-board items --status Ready --unassigned --repo <owner/repo>` (JSON lines).
  Take the highest priority (`P0` < `P1` < `P2` …), then oldest `created_at`. Prefer items
  labelled `agent-ready` when priorities tie. Skip anything labelled `needs-human`. Announce the pick in one line and go.
- Stop and report if the issue is closed, assigned to someone else, or not `Ready`.

## 2. Implement — gauntlet, ticket mode

Invoke the `francis:gauntlet` skill with `<pack?> #<n>`. Ticket mode claims the issue, branches
off `origin/<default>`, opens the draft PR with `Closes #<n>`, commits each stage locally, pushes
once at completion, and marks the PR ready. If the gauntlet ends **blocked** (`needs-human`) — including a spec gate that posted behavioural assumptions to the issue — stop here and report.

Record: PR number, branch, and the base ref `origin/<default>`.

## 3. Review ↔ fix loop

Each round uses **brand-new sub-agents** — never SendMessage to a previous round's agent.
Keep a running `ledger` of every finding so far: `{round, finding, verdict, reason/commit}`.

### 3a. Review — one fresh sub-agent running the built-in `code-review` skill

`git fetch origin`, then dispatch one fresh `general-purpose` sub-agent in the foreground
(never `run_in_background`; a background sub-agent dies or reports to the wrong session
when your turn ends). Its brief:

> Invoke the `code-review` skill at `high` on the diff `origin/<default>...HEAD` of
> branch `<branch>`. Do not use `--fix` or `--comment`; report only. Then check the diff
> against the spec below and add a finding for every acceptance criterion that is
> missing or implemented wrongly, quoting the criterion. Findings already raised and
> declined in earlier rounds are listed below with the reason. Do not repeat one unless
> the code has changed in a way that invalidates the reason.
> Tag every finding with a severity: **High**, **Medium** or **Low**. A missing or
> wrongly implemented acceptance criterion is at least Medium. Low means a minor
> defect or improvement that cannot lose data, break a criterion, or break the build.

Pass it the spec (the issue body + comments from `gh issue view <n> --comments`, plus
`.claude/specs/gauntlet/<slug>/acceptance.feature` if the gauntlet wrote one), the repo's
CLAUDE.md / AGENTS.md rules, and the declined ledger rows. Keep its report at
`.claude/specs/gauntlet/<slug>/review-round-<k>.md`.

If it reports zero findings → the loop is done (go to 4).

### 3b. Fix — one fresh `general-purpose` sub-agent

Prompt it with: the round's review report, the branch, the base ref, the spec, the repo's
test/lint/typecheck commands and byte-pin rules, and this brief:

> Triage every finding. For each, decide **FIX** or **DECLINE**. Fix hard violations and
> real spec gaps/bugs. Judgement-call smells: fix when the change is small and clearly
> better; decline when a documented repo standard endorses the code, when the fix is
> scope creep beyond the issue, or when it would churn stable code for taste. Never
> decline a missing or wrongly implemented acceptance-criterion finding without
> quoting the spec line that shows it is actually met.
> Add or adjust tests for every behavioural fix; never weaken or delete an assertion to
> go green. Run the impacted suites, typecheck and lint until green. Commit in the repo's
> Conventional Commit style (e.g. `fix(review): …`, `refactor(review): …`) — one commit
> per coherent fix. Do **not** push — every push re-runs CI (billed minutes); the
> orchestrator pushes once when the loop ends.
> Report a table: finding → FIX (commit sha) | DECLINE (one-line reason). Under 300 words.

Append its table to the ledger. Then:

- **It made zero commits** (everything declined) → loop done (go to 4).
- **Every finding this round was Low** → loop done (go to 4), even if the fixer made
  commits. Low-only fixes are not reviewed again: the severity floor, not a round
  count, is what ends the loop.
- **It made commits and the round had a High or Medium finding** → next round (back to 3a).
- **The same finding has been FIXed twice and raised a third time** → blocked: comment the ledger on the PR and issue, add `needs-human`
  (`gh label create needs-human --color B60205` if missing), `git push` so the PR holds
  the fixes, convert the PR back to draft
  (`gh pr ready <pr> --undo`), stop and report.

## 4. CI gate

Push the loop's fix commits now, in one go (`git push`) — this is the only push of the
review loop, so CI runs once on the reviewed code instead of once per fix.
`gh pr ready <pr>` if it is still a draft. Then watch in the foreground, in chunks under the
10-minute auto-background limit: `timeout 540 gh pr checks <pr> --watch --fail-fast; echo exit=$?`,
repeated while `exit=124`. Never end your turn while CI is pending — background work dies
when you return.

- Green → go to 5.
- Red → pull the failing job's log (`gh run view <run-id> --log-failed`), dispatch a
  fresh fixer (commit, no push) with the log as its only finding, then run one more review round (3a) on
  the result — a CI fix is a code change and gets reviewed like any other. Never re-run a red job hoping it flakes green without first
  reading its log; if it genuinely is a flake, say so in the final report.

## 5. Merge

No approval step — the clean review loop plus green CI is the gate.

1. Post the ledger as a plain PR comment (`gh pr comment <pr>`): rounds run, findings
   fixed/declined, CI status, and the declined findings with reasons.
2. Re-check mergeability: `gh pr view <pr> --json mergeable,mergeStateStatus,headRefOid`.
   If `origin/<default>` moved and the PR is behind or conflicting, rebase via a fresh
   fixer (it resolves conflicts itself, or uses a `resolving-merge-conflicts` skill if one is installed), push, and go back to 4.
3. `gh pr merge <pr> --squash --delete-branch --match-head-commit <headRefOid>` — the
   squash subject is the PR title, which the gauntlet wrote in commit convention.
4. Confirm Done: the issue is closed (`gh issue view <n> --json state`), and CI on the
   merge commit is green (`gh run list --branch <default> --commit <sha>`; watch it in
   the foreground with the same `timeout 540` loop). If the merge commit goes red, report it immediately — don't revert
   on your own.

## Report

Five lines at most: issue + PR link, pack, review rounds and fixed/declined counts,
CI result on the merge commit, anything declined that the user should look at.
