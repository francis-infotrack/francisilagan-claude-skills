---
type: regex
target: { source: file, path: eval-out/finisher-report.md }
pattern: 'mutant[\s\S]{0,600}(killed|surviv)|(killed|surviv)[\s\S]{0,600}mutant'
flags: i
weight: 2
---
