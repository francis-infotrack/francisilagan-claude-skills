---
description: Two-pack end to end on the pricing fixture — tests green, one commit per stage, finisher report carries CRAP numbers and mutation results.
tags: [e2e, expensive]
plugins: ["../.."]
runs: 1
max_turns: 60
timeout_seconds: 2400
allowed_tools: [Skill, Agent, Read, Glob, Grep, Write, Edit, Bash]
append_system_prompt: "Eval harness note: after the gauntlet finishes, (1) write the finisher stage's report verbatim to eval-out/finisher-report.md, and (2) run `python3 -m unittest -v > eval-out/final-tests.txt 2>&1` from the repo root. Create eval-out/ if needed; it is gitignored."
expected_outcome: gauntlet-coder then gauntlet-cleaner (composed finisher) dispatched; >= 2 new commits; eval-out/final-tests.txt ends OK with more than 2 tests; finisher report has CRAP scores and mutant results.
---

/francis:gauntlet 2 Add bulk discounts to pricing: a new order_total(unit_price_cents, quantity) returns the line total with 5% off when quantity is 10-49 and 10% off when quantity is 50 or more; below 10 there is no discount. Round half up to the whole cent.
