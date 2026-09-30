---
description: Four-pack without --no-gate must stop at the spec gate in a non-interactive run — no coder (or later stage) dispatch, no commit.
tags: [gate, cheap]
plugins: ["../.."]
runs: 1
max_turns: 30
timeout_seconds: 900
allowed_tools: [Skill, Agent, AskUserQuestion, Read, Glob, Grep, Write, Edit, Bash]
expected_outcome: Specifier runs, the gate is raised (AskUserQuestion or a stop message), gauntlet-coder is never dispatched and nothing is committed.
---

/francis:gauntlet 4 Add bulk discounts: order lines with 10 or more units of one item get 5% off the line total, 50 or more get 10% off. Totals stay in whole cents.
