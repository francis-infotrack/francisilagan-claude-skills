# skills

My Claude Code skills and agents.

## gauntlet

`/gauntlet [2|4|6] <story or #issue>` runs a feature through an "Uncle Bob" agent pipeline with deterministic quality gates. Pick the pack by stakes:

| Pack | Stages |
| --- | --- |
| 2 | coder ↔ finisher (cleaner + architect + hardener in one pass) |
| 4 | specifier → coder → refactorer → architect |
| 6 | specifier → coder → cleaner → architect → hardener → QA |

Gates: CRAP ≤ 6 on touched functions, architecture checks green, zero surviving non-equivalent mutants, and (six-pack) an executable QA run with an evidence report. Stage agents live in [`agents/`](agents). Each repo supplies its own stage → command table in its `CLAUDE.md`/`AGENTS.md`.

Given an issue reference it runs in **ticket mode**: claims the issue, opens a draft PR with `Closes #n`, and lets the repo's project-sync workflow move the board card.

## ship-ticket

`/ship-ticket` takes a GitHub issue from Ready to merged with no human in the loop: gauntlet in ticket mode, then repeated fresh reviews (the built-in `code-review` skill plus an acceptance-criteria check) and fixers until a round finds nothing, then CI and squash-merge.

## gh-board

`bin/gh-board` → `lib/gh_board.py`: a small GitHub Projects v2 client (`items`, `field`, `status`, `add`) that ticket mode uses to read Effort and move cards. Env: `BOARD_OWNER`, `BOARD_TITLE`.

## Install

```bash
git clone https://github.com/francis-infotrack/skills ~/Code/skills
~/Code/skills/install.sh   # symlinks skills, agents and gh-board into place
```

Requires `gh` (authenticated) and Python 3.11+.
