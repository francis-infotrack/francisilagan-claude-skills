---
description: Four-pack with --no-gate must skip the question and proceed from specifier to coder. Graded on dispatch order only, so a timeout after the coder starts still passes.
tags: [gate, medium-cost]
plugins: ["../.."]
runs: 1
max_turns: 40
timeout_seconds: 900
allowed_tools: [Skill, Agent, AskUserQuestion, Read, Glob, Grep, Write, Edit, Bash]
expected_outcome: No AskUserQuestion; gauntlet-specifier dispatched before gauntlet-coder.
---

/francis:gauntlet 4 --no-gate Add bulk discounts: order lines with 10 or more units of one item get 5% off the line total, 50 or more get 10% off. Totals stay in whole cents.
