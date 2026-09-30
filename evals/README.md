# Gauntlet regression evals

A small `claude plugin eval` suite for the `francis` plugin, so prompt changes to
`skills/gauntlet/SKILL.md` and `agents/gauntlet-*.md` can be checked before release.
Format reference: <https://code.claude.com/docs/en/plugin-evals>.

**Requires Claude Code v2.1.269+.** Older builds (2.1.258 was tested) print
"`plugin eval` is currently in early access" and run nothing; run `claude update`.

## Layout

```
evals/
├── fixtures/
│   ├── pricing/          # vendored fixture project: pricing.py, test_pricing.py, CLAUDE.md
│   └── seed-pricing.sh   # copies it into the run workspace, git init on main, 1 commit, offline bare origin
├── <case>/
│   ├── prompt.md         # frontmatter = run limits/tools; body = the prompt
│   ├── case.yaml         # context.scaffold_script only
│   ├── scaffold.sh       # calls ../fixtures/seed-pricing.sh
│   └── graders/*.md      # one grader per file
└── results/              # written by runs; gitignored
```

All graders are deterministic (`regex`, `tool_used`, `tool_order`) — no LLM judge, so
no judge cost. Graders read `.git/logs/HEAD` to count commits, because the harness
has no command-running graders.

## Cases

| Case | Covers | Rough cost / time |
|---|---|---|
| `specifier-only` | Dispatches `francis:gauntlet-specifier` directly on an ambiguous request. Checks `acceptance.feature` has `bulk-discount-<n>` IDs and a `Scenario Outline` + `Examples`, `qa-procedure.md` has `## Assumptions` with `[behavioural]` tags, the report has a requirement → evidence table, and no `.py` file was created. | ~$1.60, ~3 min (measured) |
| `spec-gate-stops` | `/francis:gauntlet 4 …` with no `--no-gate`. The run is non-interactive, so it must stop at the gate: specifier dispatched, **no** coder/cleaner/architect/hardener/qa dispatch (weight 3), no commit after the seed, and AskUserQuestion was attempted. | ~$2–3, ~5 min (est.) |
| `spec-gate-no-gate` | `/francis:gauntlet 4 --no-gate …`: no AskUserQuestion, and specifier is dispatched before coder. Graded on dispatch order only; the 900 s timeout may cut the pack short and still pass. | ~$4–8, ≤15 min (est.) |
| `two-pack-e2e` | `/francis:gauntlet 2 …` on the fixture: coder then the composed finisher (cleaner), no specifier, ≥2 new commits, final `unittest` run is OK with more than the fixture's 2 tests, and the finisher report has CRAP numbers and killed/survived mutants. An `append_system_prompt` asks the orchestrator to write `eval-out/final-tests.txt` and `eval-out/finisher-report.md` so graders can read them. | ~$8–20, 15–40 min (est.) |

Not covered: **ticket mode** (the behavioural-assumption → `needs-human` path). It
shells out to `gh` and `gh-board`, and a run can't fake them. The run's `PATH` comes
from your shell and can't be changed per case (only `EVAL_*` variables pass through).
The OS sandbox also blocks network access, and MCP mocks cover MCP tools only, not
CLIs. To test ticket mode, move the GitHub calls behind an MCP server, or
run `tests/` with the `gh` fake.

## Running

From the repo root. Bash, Write and Edit need an explicit grant, the fixture needs
`--scaffold`, and `--ablation none` skips the no-plugin baseline. The baseline
isn't useful here, since the no-plugin arm can't dispatch `francis:*` agents.

```bash
# whole suite (expensive — mostly two-pack-e2e)
claude plugin eval . --scaffold --ablation none --allow-tools Bash Write Edit \
  --no-publish --max-cost-usd 40

# one case
claude plugin eval . --case specifier-only --runs 1 --scaffold --ablation none \
  --allow-tools Bash Write Edit --no-publish

# cheap regression gate only
claude plugin eval . --tag cheap --scaffold --ablation none --allow-tools Bash Write Edit
```

Each case sets `runs: 1` to keep costs down. Before trusting a change, confirm it
with `--runs 3`. Pin `--model` when you compare scores over time. Add
`--keep-temp` to inspect the workspace a run left behind.

Linux sandbox prerequisites: `bubblewrap` and `socat`.
