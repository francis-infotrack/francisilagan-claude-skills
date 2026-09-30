# francisilagan-claude-skills

A Claude Code plugin (`francis`) with my agent gauntlet and ship-ticket skills. The repo is also its own plugin marketplace (`francisilagan`).

## Install

```bash
claude plugin marketplace add francis-infotrack/francisilagan-claude-skills
claude plugin install francis@francisilagan
```

Or inside a session: `/plugin marketplace add francis-infotrack/francisilagan-claude-skills`, then `/plugin install francis@francisilagan`.

Update after new commits land:

```bash
claude plugin marketplace update francisilagan
claude plugin update francis@francisilagan
```

Requires `gh` (authenticated) and Python 3.11+.

## gauntlet

`/francis:gauntlet [2|4|6] <story or #issue>` runs a feature through an "Uncle Bob" agent pipeline with deterministic quality gates. Pick the pack by stakes:

| Pack | Stages |
| --- | --- |
| 2 | coder ↔ finisher (cleaner + architect + hardener in one pass) |
| 4 | specifier → coder → refactorer → architect |
| 6 | specifier → coder → cleaner → architect → hardener → QA |

Gates: CRAP ≤ 6 on touched functions, architecture checks green, zero surviving non-equivalent mutants, and (six-pack) an executable QA run with an evidence report. The stage subagents (`francis:gauntlet-specifier`, `-coder`, `-cleaner`, `-architect`, `-hardener`, `-qa`) live in [`agents/`](agents). Each repo supplies its own stage → command table in its `CLAUDE.md`/`AGENTS.md`.

Given an issue reference it runs in **ticket mode**: claims the issue, opens a draft PR with `Closes #n`, and lets the repo's project-sync workflow move the board card.

## ship-ticket

`/francis:ship-ticket [#issue] [2|4|6]` takes a GitHub issue from Ready to merged with no human in the loop: gauntlet in ticket mode, then repeated fresh reviews (the built-in `code-review` skill plus an acceptance-criteria check) and fixers until a round finds nothing, then CI and squash-merge.

## gh-board

`bin/gh-board` (on the Bash tool's `PATH` while the plugin is enabled) → `lib/gh_board.py`: a small GitHub Projects v2 client (`items`, `field`, `status`, `add`) that ticket mode uses to read Effort and move cards. Env: `BOARD_OWNER`, `BOARD_TITLE`.

## Development

```bash
claude plugin validate . --strict
python3 -m unittest discover -s tests
```
