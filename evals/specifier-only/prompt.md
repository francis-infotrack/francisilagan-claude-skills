---
description: Dispatch francis:gauntlet-specifier alone on an ambiguous one-paragraph request; grade the Gherkin and QA procedure it writes.
tags: [specifier, cheap, smoke]
plugins: ["../.."]
runs: 1
max_turns: 15
timeout_seconds: 600
allowed_tools: [Agent, Read, Glob, Grep, Write, Bash]
expected_outcome: specs/bulk-discount/acceptance.feature with bulk-discount-<n> IDs and a Scenario Outline; qa-procedure.md with tagged assumptions; a requirement → evidence table in the report.
---

Dispatch the `francis:gauntlet-specifier` agent (full mode: both acceptance.feature and qa-procedure.md) for the feature request below. Story slug: `bulk-discount`. Specs directory: `specs/bulk-discount/`. Do not change any code yourself. When the agent returns, reply with its report verbatim and nothing else.

Feature request: Customers buying in bulk should pay less. When an order line has a lot of units of the same item, knock a percentage off that line's total, and give a bigger percentage for really big orders. Small orders must be priced exactly as today, and the discounted total should still be in whole cents.
