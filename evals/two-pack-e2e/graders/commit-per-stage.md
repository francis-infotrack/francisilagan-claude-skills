---
type: regex
target: { source: file, path: .git/logs/HEAD }
pattern: '(\tcommit: [\s\S]*){2}'
weight: 2
---
